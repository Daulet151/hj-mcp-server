"""
Conversation Context
Extended context storage for conversational AI
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger(__name__, "INFO")


class ConversationContext:
    """
    Stores conversation state and data for a single user/channel pair.

    Maintains:
    - Conversation history (messages)
    - Last DataFrame and SQL query
    - Last analysis text
    - Timestamps for cleanup
    """

    def __init__(self, timeout_minutes: int = 30):
        """
        Initialize conversation context.

        Args:
            timeout_minutes: Auto-clear context after this many minutes of inactivity
        """
        self.timeout_minutes = timeout_minutes

        # Conversation history
        self.history: List[Dict[str, str]] = []  # [{"role": "user/assistant", "content": "..."}]

        # Data from last analytical query
        self.last_dataframe: Optional[pd.DataFrame] = None
        self.last_sql: Optional[str] = None
        self.last_analysis: Optional[str] = None
        self.last_user_query: Optional[str] = None

        # Timestamps
        self.created_at = datetime.now()
        self.last_activity = datetime.now()

    def add_user_message(self, message: str):
        """
        Add user message to history.

        Args:
            message: User's message
        """
        self.history.append({"role": "user", "content": message})
        self.last_user_query = message
        self.last_activity = datetime.now()
        logger.debug(f"Added user message. History size: {len(self.history)}")

    def add_bot_message(self, message: str):
        """
        Add bot response to history.

        Args:
            message: Bot's response
        """
        self.history.append({"role": "assistant", "content": message})
        self.last_activity = datetime.now()
        logger.debug(f"Added bot message. History size: {len(self.history)}")

    def save_data(
        self,
        dataframe: pd.DataFrame,
        sql_query: str,
        analysis: str
    ):
        """
        Save data from analytical query.

        Args:
            dataframe: Query results
            sql_query: SQL that was executed
            analysis: Analysis text
        """
        self.last_dataframe = dataframe.copy()  # Copy to avoid mutation
        self.last_sql = sql_query
        self.last_analysis = analysis
        self.last_activity = datetime.now()
        logger.info(f"Saved data: {len(dataframe)} rows, {len(dataframe.columns)} columns")

    def has_dataframe(self) -> bool:
        """
        Check if there's a DataFrame in memory.

        Returns:
            True if DataFrame exists
        """
        return self.last_dataframe is not None and not self.last_dataframe.empty

    def get_recent_history(self, n: int = 10) -> List[Dict]:
        """
        Get last N messages from history.

        Args:
            n: Number of messages to return

        Returns:
            List of recent messages
        """
        return self.history[-n:] if len(self.history) > n else self.history.copy()

    def clear_data(self):
        """
        Clear data but keep conversation history.
        Useful when user wants to start a new query but continue conversation.
        """
        self.last_dataframe = None
        self.last_sql = None
        self.last_analysis = None
        logger.info("Cleared data (kept history)")

    def clear_all(self):
        """
        Clear everything - data and history.
        """
        self.history.clear()
        self.last_dataframe = None
        self.last_sql = None
        self.last_analysis = None
        self.last_user_query = None
        self.last_activity = datetime.now()
        logger.info("Cleared all context")

    def is_expired(self) -> bool:
        """
        Check if context has expired due to inactivity.

        Returns:
            True if context should be cleared
        """
        inactive_time = datetime.now() - self.last_activity
        is_expired = inactive_time > timedelta(minutes=self.timeout_minutes)

        if is_expired:
            logger.info(f"Context expired after {inactive_time.total_seconds()/60:.1f} minutes")

        return is_expired

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of context state for logging/debugging.

        Returns:
            Dictionary with context summary
        """
        return {
            "history_size": len(self.history),
            "has_dataframe": self.has_dataframe(),
            "dataframe_shape": self.last_dataframe.shape if self.has_dataframe() else None,
            "has_sql": self.last_sql is not None,
            "has_analysis": self.last_analysis is not None,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "age_minutes": (datetime.now() - self.created_at).total_seconds() / 60,
            "inactive_minutes": (datetime.now() - self.last_activity).total_seconds() / 60
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        summary = self.get_summary()
        return (
            f"ConversationContext("
            f"history={summary['history_size']} msgs, "
            f"has_data={summary['has_dataframe']}, "
            f"age={summary['age_minutes']:.1f}m, "
            f"inactive={summary['inactive_minutes']:.1f}m)"
        )
