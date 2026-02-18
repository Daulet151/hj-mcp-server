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
        self.db_manager = db_manager

        # Conversation state management (in-memory cache, backed by PostgreSQL)
        # Key: (user_id, channel_id), Value: {state, last_query, ...}
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
            - query_type: Type of query (informational, data_extraction, or None)
        """
        conversation_key = (user_id, channel_id)
        conversation = self._get_conversation(user_id, channel_id)

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
                query_type = conversation.get("query_type")

                logger.info("User confirmed table generation")
                self._reset_conversation(conversation_key)

                # Return data context so app.py can use cached results
                data_context = {
                    "dataframe": dataframe,
                    "sql_query": sql_query
                }

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
    ) -> Tuple[str, bool, str]:
        """Process new user query with conversation context.

        Returns:
            Tuple of (response, should_generate, query_type)
        """
        user_id, channel_id = conversation_key

        # Build conversation context from recent interactions
        conversation_context = self._build_conversation_context(user_id, channel_id)

        # Classify query with context
        query_type = self.classifier.classify(user_message, conversation_context)
        logger.info(f"Query classified as: {query_type}")

        if query_type == "informational":
            # Handle informational query
            response = self.informational_agent.respond(user_message)
            self._reset_conversation(conversation_key)
            return (response, False, query_type)

        elif query_type in ("data_extraction", "follow_up"):
            # Handle data extraction or follow-up query with context
            analysis, dataframe, sql_query = self.analytical_agent.analyze(
                user_message, conversation_context
            )

            # Update conversation state - waiting for confirmation
            # Store dataframe and sql_query so we don't need to regenerate
            self.conversations[conversation_key] = {
                "state": ConversationState.WAITING_FOR_CONFIRMATION,
                "last_query": user_message,
                "dataframe": dataframe,
                "sql_query": sql_query,
                "query_type": "data_extraction"  # normalize follow_up to data_extraction
            }

            # Persist state to survive restarts
            self.db_manager.save_conversation_state(
                user_id=user_id,
                channel_id=channel_id,
                state="waiting_for_confirmation",
                last_query=user_message,
                last_sql_query=sql_query,
                query_type="data_extraction"
            )

            return (analysis, False, "data_extraction")

        # Fallback
        return (
            "Извините, я не совсем понял ваш запрос. Попробуйте переформулировать? 🤔",
            False,
            "unknown"
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
        """Reset conversation state to initial (in-memory and DB)."""
        self.conversations[conversation_key] = {
            "state": ConversationState.INITIAL,
            "last_query": None
        }
        user_id, channel_id = conversation_key
        self.db_manager.save_conversation_state(
            user_id=user_id,
            channel_id=channel_id,
            state="initial"
        )

    def _get_conversation(self, user_id: str, channel_id: str) -> Dict[str, Any]:
        """
        Get conversation state, loading from DB if not in memory.

        Args:
            user_id: Slack user ID
            channel_id: Slack channel ID

        Returns:
            Conversation state dict
        """
        key = (user_id, channel_id)
        if key not in self.conversations:
            # Try loading from database
            persisted = self.db_manager.load_conversation_state(user_id, channel_id)
            if persisted and persisted.get("state") != "initial":
                self.conversations[key] = {
                    "state": ConversationState(persisted["state"]),
                    "last_query": persisted.get("last_query"),
                    "dataframe": None,  # Cannot persist DataFrames; user re-asks if restart happened
                    "sql_query": persisted.get("last_sql_query"),
                    "query_type": persisted.get("last_query_type"),
                }
                logger.info(f"Loaded persisted conversation state: {persisted['state']}")
            else:
                self.conversations[key] = {
                    "state": ConversationState.INITIAL,
                    "last_query": None,
                    "dataframe": None,
                    "sql_query": None,
                    "query_type": None
                }
        return self.conversations[key]

    def _build_conversation_context(self, user_id: str, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        Build conversation context from recent interactions for multi-turn queries.

        Args:
            user_id: Slack user ID
            channel_id: Slack channel ID

        Returns:
            Dict with history, previous_question, previous_sql or None if no recent history
        """
        recent = self.db_manager.get_recent_interactions(user_id, channel_id, limit=5, minutes=30)
        if not recent:
            return None

        # Find the last interaction that had a SQL query
        last_data_interaction = None
        for interaction in reversed(recent):
            if interaction.get("sql_query"):
                last_data_interaction = interaction
                break

        context = {
            "history": recent,
            "previous_question": recent[-1]["user_message"] if recent else None,
            "previous_sql": last_data_interaction["sql_query"] if last_data_interaction else None,
        }

        logger.info(f"Built conversation context: {len(recent)} recent interactions, has_previous_sql={context['previous_sql'] is not None}")
        return context

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
