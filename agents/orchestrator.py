"""
Agent Orchestrator
Coordinates all agents and manages conversation state
"""
from typing import Dict, Any, Optional, Tuple
from enum import Enum
from .classifier import QueryClassifier
from .informational_agent import InformationalAgent
from .analytical_agent import AnalyticalAgent
from utils.logger import setup_logger

logger = setup_logger(__name__, "INFO")


class ConversationState(Enum):
    """Possible states of conversation."""
    INITIAL = "initial"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    GENERATING_TABLE = "generating_table"


class AgentOrchestrator:
    """Orchestrates multiple agents and manages conversation flow."""

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
        self.classifier = QueryClassifier(api_key, model)
        self.informational_agent = InformationalAgent(api_key, model)
        self.analytical_agent = AnalyticalAgent(
            api_key,
            schema_docs,
            sql_generator,
            db_manager,
            model
        )

        # Conversation state management
        # Key: (user_id, channel_id), Value: {state, last_query}
        self.conversations: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def process_message(
        self,
        user_message: str,
        user_id: str,
        channel_id: str
    ) -> Tuple[str, bool, Optional[Any], Optional[str], Optional[str]]:
        """
        Process user message and return appropriate response.

        Args:
            user_message: User's message
            user_id: Slack user ID
            channel_id: Slack channel ID

        Returns:
            Tuple of (response_text, should_generate_table, data_context, original_query, query_type)
            - response_text: Text to send to user
            - should_generate_table: True if we should generate Excel table
            - data_context: Dict with 'dataframe' and 'sql_query' (if available from analysis)
            - original_query: Original user query for table generation (None if not applicable)
            - query_type: Type of query ('informational', 'data_extraction', or None for confirmation)
        """
        conversation_key = (user_id, channel_id)
        conversation = self.conversations.get(conversation_key, {
            "state": ConversationState.INITIAL,
            "last_query": None,
            "dataframe": None,
            "sql_query": None,
            "query_type": None
        })

        current_state = conversation["state"]
        logger.info(f"Processing message in state: {current_state.value}")

        # Check if user is confirming table generation
        if current_state == ConversationState.WAITING_FOR_CONFIRMATION:
            is_confirmation = self._is_confirmation(user_message)

            if is_confirmation:
                # User confirmed - generate table
                # Save data BEFORE resetting conversation
                original_query = conversation.get("last_query")
                dataframe = conversation.get("dataframe")
                sql_query = conversation.get("sql_query")

                logger.info("User confirmed table generation")
                self._reset_conversation(conversation_key)

                # Return data context so app.py can use cached results
                data_context = {
                    "dataframe": dataframe,
                    "sql_query": sql_query
                }

                query_type = conversation.get("query_type")

                return (
                    "Отлично! Генерирую таблицу для вас... ⏳",
                    True,  # Should generate table
                    data_context,  # Cached data from analysis
                    original_query,  # Original query
                    query_type  # Query type
                )
            else:
                # User declined or asked something else
                logger.info("User declined or asked new question")
                self._reset_conversation(conversation_key)
                # Process as new query
                response, should_generate, query_type = self._process_new_query(user_message, conversation_key)
                return (response, should_generate, None, None, query_type)

        # Process new query
        response, should_generate, query_type = self._process_new_query(user_message, conversation_key)
        return (response, should_generate, None, None, query_type)

    def _process_new_query(
        self,
        user_message: str,
        conversation_key: Tuple[str, str]
    ) -> Tuple[str, bool, Optional[str]]:
        """Process new user query."""
        # Classify query
        query_type = self.classifier.classify(user_message)
        logger.info(f"Query classified as: {query_type}")

        if query_type == "informational":
            # Handle informational query
            response = self.informational_agent.respond(user_message)
            self._reset_conversation(conversation_key)
            return (response, False, query_type)

        elif query_type == "data_extraction":
            # Handle data extraction query - now returns analysis, dataframe, and sql
            analysis, dataframe, sql_query = self.analytical_agent.analyze(user_message)

            # Update conversation state - waiting for confirmation
            # Store dataframe and sql_query so we don't need to regenerate
            self.conversations[conversation_key] = {
                "state": ConversationState.WAITING_FOR_CONFIRMATION,
                "last_query": user_message,
                "dataframe": dataframe,
                "sql_query": sql_query,
                "query_type": query_type
            }

            return (analysis, False, query_type)

        # Fallback
        return (
            "Извините, я не совсем понял ваш запрос. Попробуйте переформулировать? 🤔",
            False,
            None
        )

    def _is_confirmation(self, message: str) -> bool:
        """
        Check if message is a confirmation for table generation.

        Args:
            message: User's message

        Returns:
            True if message is confirmation, False otherwise
        """
        message_lower = message.lower().strip()

        # Positive confirmations
        positive_keywords = [
            "да", "yes", "конечно", "давай", "давайте", "ок",
            "хорошо", "согласен", "подтверждаю", "генерируй",
            "сгенерируй", "выгрузи", "сделай", "вперед", "го",
            "ага", "угу", "ага давай", "ага конечно", "ага да",
            "+", "✓", "👍", "okay", "ok"
        ]

        # Negative keywords
        negative_keywords = [
            "нет", "no", "не надо", "не нужно", "отмена", "стоп"
        ]

        # Check for negative first
        for keyword in negative_keywords:
            if keyword in message_lower:
                return False

        # Check for positive
        for keyword in positive_keywords:
            if keyword in message_lower:
                return True

        # If message is very short and positive-like
        if len(message_lower) <= 5 and message_lower in ["да", "yes", "ок", "ok", "+", "ага", "угу"]:
            return True

        return False

    def _reset_conversation(self, conversation_key: Tuple[str, str]):
        """Reset conversation state to initial."""
        self.conversations[conversation_key] = {
            "state": ConversationState.INITIAL,
            "last_query": None
        }

    def get_last_query(self, user_id: str, channel_id: str) -> Optional[str]:
        """
        Get the last query from user for table generation.

        Args:
            user_id: Slack user ID
            channel_id: Slack channel ID

        Returns:
            Last query text or None
        """
        conversation_key = (user_id, channel_id)
        conversation = self.conversations.get(conversation_key)

        if conversation:
            return conversation.get("last_query")

        return None
