"""
Enhanced Agent Orchestrator with Conversational Memory
Coordinates all agents and manages conversation state with ChatGPT-like continuity
"""
from typing import Dict, Any, Optional, Tuple
from .classifier import QueryClassifier  # Keep old classifier as fallback
from .smart_classifier import SmartIntentClassifier  # New smart classifier
from .informational_agent import InformationalAgent
from .analytical_agent import AnalyticalAgent
from .continuation_agent import ContinuationAgent  # New agent for follow-ups
from .conversation_context import ConversationContext  # New context storage
from utils.logger import setup_logger

logger = setup_logger(__name__, "INFO")


class AgentOrchestrator:
    """
    Enhanced orchestrator with conversational memory and context awareness.

    New features:
    - Maintains conversation history
    - Handles follow-up questions using data in memory
    - Smart intent detection with context
    - ChatGPT-like natural conversation flow
    """

    def __init__(
        self,
        api_key: str,
        schema_docs: Dict[str, Any],
        sql_generator,
        db_manager,
        model: str = "gpt-4o"
    ):
        """
        Initialize orchestrator with all agents.

        Args:
            api_key: OpenAI API key
            schema_docs: Schema documentation from YML files
            sql_generator: SQLGenerator instance
            db_manager: DatabaseManager instance
            model: Model to use for agents
        """
        # Existing agents (keep backward compatibility)
        self.basic_classifier = QueryClassifier(api_key, model)
        self.informational_agent = InformationalAgent(api_key, model)
        self.analytical_agent = AnalyticalAgent(
            api_key,
            schema_docs,
            sql_generator,
            db_manager,
            model
        )

        # NEW: Smart agents for conversational flow
        self.smart_classifier = SmartIntentClassifier(api_key, model)
        self.continuation_agent = ContinuationAgent(api_key, model)

        # NEW: Enhanced conversation storage
        # Key: (user_id, channel_id), Value: ConversationContext
        self.conversations: Dict[Tuple[str, str], ConversationContext] = {}

    def process_message(
        self,
        user_message: str,
        user_id: str,
        channel_id: str
    ) -> Tuple[str, bool, Optional[Any], Optional[str], Optional[str]]:
        """
        Process user message and return appropriate response.

        ENHANCED: Now handles conversational follow-ups and context.

        Args:
            user_message: User's message
            user_id: Slack user ID
            channel_id: Slack channel ID

        Returns:
            Tuple of (response_text, should_generate_table, data_context, original_query, query_type)
            - response_text: Text to send to user
            - should_generate_table: True if we should generate Excel table
            - data_context: Dict with 'dataframe' and 'sql_query' (if available)
            - original_query: Original user query for table generation
            - query_type: Type of query (informational, data_extraction, continuation, table_request)
        """
        conversation_key = (user_id, channel_id)

        # Get or create conversation context
        if conversation_key not in self.conversations:
            self.conversations[conversation_key] = ConversationContext(timeout_minutes=30)
            logger.info(f"Created new conversation context for {conversation_key}")

        context = self.conversations[conversation_key]

        # Check if context expired due to inactivity
        if context.is_expired():
            logger.info(f"Context expired for {conversation_key}, resetting")
            context.clear_all()

        # Add user message to history
        context.add_user_message(user_message)

        logger.info(f"Processing message. Context: {context}")

        # FAST PATH: Check for simple confirmations first
        if self.smart_classifier.is_simple_confirmation(user_message):
            if context.has_dataframe():
                logger.info("Simple confirmation detected -> generating table")
                return self._handle_table_request(context, user_message)
            else:
                logger.info("Confirmation but no data -> informational response")
                response = "У меня нет данных для генерации таблицы. Задайте сначала аналитический запрос."
                context.add_bot_message(response)
                return (response, False, None, None, "informational")

        # FAST PATH: Check for simple rejections
        if self.smart_classifier.is_simple_rejection(user_message):
            logger.info("Simple rejection detected")
            response = "Хорошо, не буду генерировать таблицу. Чем ещё могу помочь?"
            context.add_bot_message(response)
            context.clear_data()  # Clear data but keep history
            return (response, False, None, None, "informational")

        # SMART CLASSIFICATION: Determine intent with context
        intent = self.smart_classifier.classify_with_context(
            user_message=user_message,
            conversation_history=context.get_recent_history(),
            has_pending_data=context.has_dataframe()
        )

        logger.info(f"Intent classified as: {intent}")

        # Route to appropriate handler
        if intent == "continuation":
            return self._handle_continuation(context, user_message)

        elif intent == "table_request":
            return self._handle_table_request(context, user_message)

        elif intent == "new_data_query":
            return self._handle_new_data_query(context, user_message)

        elif intent == "informational":
            return self._handle_informational(context, user_message)

        else:
            # Fallback
            response = "Извините, я не совсем понял ваш запрос. Попробуйте переформулировать? 🤔"
            context.add_bot_message(response)
            return (response, False, None, None, "unknown")

    def _handle_continuation(
        self,
        context: ConversationContext,
        user_message: str
    ) -> Tuple[str, bool, Optional[Any], Optional[str], str]:
        """
        Handle follow-up question using data in memory.

        Args:
            context: Conversation context
            user_message: User's follow-up question

        Returns:
            Response tuple
        """
        logger.info("Handling continuation (follow-up question)")

        if not context.has_dataframe():
            logger.warning("Continuation requested but no data in memory")
            response = "К сожалению, у меня нет данных для ответа на этот вопрос. Можете задать новый аналитический запрос?"
            context.add_bot_message(response)
            return (response, False, None, None, "continuation")

        try:
            # Use continuation agent to answer
            answer = self.continuation_agent.answer_followup(
                user_question=user_message,
                previous_dataframe=context.last_dataframe,
                previous_sql=context.last_sql,
                previous_analysis=context.last_analysis,
                conversation_history=context.get_recent_history()
            )

            context.add_bot_message(answer)
            logger.info(f"Generated continuation answer ({len(answer)} chars)")

            return (answer, False, None, None, "continuation")

        except Exception as e:
            logger.error(f"Error in continuation handling: {e}")
            response = "Извините, произошла ошибка при обработке вашего вопроса. Попробуйте задать новый запрос."
            context.add_bot_message(response)
            return (response, False, None, None, "continuation")

    def _handle_table_request(
        self,
        context: ConversationContext,
        user_message: str
    ) -> Tuple[str, bool, Optional[Any], Optional[str], str]:
        """
        Handle request to generate Excel table.

        Args:
            context: Conversation context
            user_message: User's message

        Returns:
            Response tuple with table generation flag
        """
        logger.info("Handling table generation request")

        if not context.has_dataframe():
            response = "У меня нет данных для генерации таблицы. Задайте сначала аналитический запрос."
            context.add_bot_message(response)
            return (response, False, None, None, "table_request")

        # Prepare data context for Excel generation
        data_context = {
            "dataframe": context.last_dataframe,
            "sql_query": context.last_sql
        }

        response = "Отлично! Генерирую таблицу для вас... ⏳"
        context.add_bot_message(response)

        # Don't clear data immediately - might ask follow-ups about the table
        logger.info(f"Returning data for table generation ({len(context.last_dataframe)} rows)")

        return (
            response,
            True,  # Should generate table
            data_context,
            context.last_user_query,
            "table_request"
        )

    def _handle_new_data_query(
        self,
        context: ConversationContext,
        user_message: str
    ) -> Tuple[str, bool, Optional[Any], Optional[str], str]:
        """
        Handle new data extraction query.

        Args:
            context: Conversation context
            user_message: User's query

        Returns:
            Response tuple
        """
        logger.info("Handling new data extraction query")

        try:
            # Use analytical agent (existing functionality)
            analysis, dataframe, sql_query = self.analytical_agent.analyze(user_message)

            # Save data to context
            context.save_data(
                dataframe=dataframe,
                sql_query=sql_query,
                analysis=analysis
            )

            context.add_bot_message(analysis)
            logger.info(f"Analysis complete: {len(dataframe)} rows, {len(dataframe.columns)} columns")

            return (analysis, False, None, None, "data_extraction")

        except Exception as e:
            logger.error(f"Error in data extraction: {e}")
            response = f"Извините, произошла ошибка при обработке запроса: {str(e)}"
            context.add_bot_message(response)
            return (response, False, None, None, "data_extraction")

    def _handle_informational(
        self,
        context: ConversationContext,
        user_message: str
    ) -> Tuple[str, bool, Optional[Any], Optional[str], str]:
        """
        Handle informational query about bot functionality.

        Args:
            context: Conversation context
            user_message: User's question

        Returns:
            Response tuple
        """
        logger.info("Handling informational query")

        try:
            # Use informational agent (existing functionality)
            response = self.informational_agent.respond(user_message)
            context.add_bot_message(response)
            return (response, False, None, None, "informational")

        except Exception as e:
            logger.error(f"Error in informational handling: {e}")
            response = "Извините, произошла ошибка. Попробуйте ещё раз."
            context.add_bot_message(response)
            return (response, False, None, None, "informational")

    def cleanup_expired_contexts(self):
        """
        Clean up expired conversation contexts.
        Should be called periodically (e.g., every hour).
        """
        expired_keys = [
            key for key, context in self.conversations.items()
            if context.is_expired()
        ]

        for key in expired_keys:
            logger.info(f"Cleaning up expired context for {key}")
            del self.conversations[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired contexts")

    def get_context_summary(self, user_id: str, channel_id: str) -> Optional[Dict]:
        """
        Get summary of conversation context for debugging.

        Args:
            user_id: Slack user ID
            channel_id: Slack channel ID

        Returns:
            Context summary dict or None
        """
        context = self.conversations.get((user_id, channel_id))
        return context.get_summary() if context else None

    # Legacy method for backward compatibility
    def get_last_query(self, user_id: str, channel_id: str) -> Optional[str]:
        """
        Get the last query from user (backward compatibility).

        Args:
            user_id: Slack user ID
            channel_id: Slack channel ID

        Returns:
            Last query text or None
        """
        context = self.conversations.get((user_id, channel_id))
        return context.last_user_query if context else None
