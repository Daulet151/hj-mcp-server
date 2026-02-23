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
    GENERATING_TABLE = "generating_table"


class AgentOrchestrator:
    """Orchestrates multiple agents and manages conversation flow."""

    def __init__(
        self,
        api_key: str,
        schema_docs: Dict[str, Any],
        sql_generator,
        db_manager,
        model: str = "claude-sonnet-4-5-20250929"
    ):
        """
        Initialize orchestrator with all agents.

        Args:
            api_key: Anthropic API key
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

        # Conversation state management (in-memory cache)
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
        """
        # Build conversation context from recent interactions
        conversation_context = self._build_conversation_context(user_id, channel_id)

        # Classify query with context
        query_type = self.classifier.classify(user_message, conversation_context)
        logger.info(f"Query classified as: {query_type}")

        if query_type == "informational":
            response = self.informational_agent.respond(user_message)
            return (response, False, None, None, query_type)

        # data_extraction or follow_up
        analysis, dataframe, sql_query = self.analytical_agent.analyze(
            user_message, conversation_context
        )

        # Check if user explicitly wants Excel
        wants_excel = self._wants_excel(user_message)

        if wants_excel and dataframe is not None:
            data_context = {
                "dataframe": dataframe,
                "sql_query": sql_query
            }
            return (analysis, True, data_context, user_message, "data_extraction")

        return (analysis, False, None, None, "data_extraction")

    def _wants_excel(self, message: str) -> bool:
        """Check if user explicitly asks for Excel/table export."""
        keywords = [
            "выгрузи", "скачать", "таблица", "таблицу", "excel",
            "эксель", "файл", "экспорт", "xlsx", "выгрузка",
            "сгенерируй таблицу", "сделай таблицу", "скачай"
        ]
        message_lower = message.lower()
        return any(kw in message_lower for kw in keywords)

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
