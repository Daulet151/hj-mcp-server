"""
Database connection and query execution.
"""
import psycopg2
import pandas as pd
from typing import Union, Dict, Any
from contextlib import contextmanager
from utils.logger import setup_logger

logger = setup_logger(__name__)


class DatabaseManager:
    """Manages PostgreSQL database connections and query execution."""

    def __init__(self, host: str, dbname: str, user: str, password: str, port: int = 5432,
                 query_timeout: int = 60):
        """
        Initialize database manager.

        Args:
            host: Database host
            dbname: Database name
            user: Database user
            password: Database password
            port: Database port (default: 5432)
            query_timeout: Query timeout in seconds (default: 60)
        """
        self.config = {
            "host": host,
            "dbname": dbname,
            "user": user,
            "password": password,
            "port": port,
            "connect_timeout": 10  # Connection timeout
        }
        self.query_timeout = query_timeout

    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.

        Yields:
            psycopg2 connection object

        Example:
            with db.get_connection() as conn:
                # use connection
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.config)
            logger.debug("Database connection established")
            yield conn
        except psycopg2.Error as e:
            logger.error("Database connection error: %s", str(e))
            raise
        finally:
            if conn:
                conn.close()
                logger.debug("Database connection closed")

    def execute_query(self, sql: str) -> pd.DataFrame:
        """
        Execute SQL query and return results as DataFrame.

        Args:
            sql: SQL query string

        Returns:
            pandas DataFrame with query results

        Raises:
            psycopg2.Error: If query execution fails
        """
        logger.info("Executing SQL query")
        logger.debug("SQL: %s", sql[:200])

        try:
            with self.get_connection() as conn:
                # Set statement timeout to prevent long-running queries
                with conn.cursor() as cur:
                    cur.execute(f"SET statement_timeout = '{self.query_timeout}s'")
                    logger.debug("Set query timeout to %d seconds", self.query_timeout)

                df = pd.read_sql(sql, conn)

                logger.info(
                    "Query executed successfully: %d rows, %d columns",
                    len(df),
                    len(df.columns)
                )

                return df

        except psycopg2.Error as e:
            logger.error("Query execution failed: %s", str(e))
            raise

    def test_connection(self) -> bool:
        """
        Test database connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    logger.info("Database connection test successful")
                    return result[0] == 1
        except Exception as e:
            logger.error("Database connection test failed: %s", str(e))
            return False

    def get_table_info(self, schema: str = "olap_schema") -> pd.DataFrame:
        """
        Get information about tables in the schema.

        Args:
            schema: Database schema name

        Returns:
            DataFrame with table information
        """
        sql = f"""
        SELECT
            table_name,
            column_name,
            data_type,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = '{schema}'
        ORDER BY table_name, ordinal_position
        """

        return self.execute_query(sql)

    def log_bot_user(self, user_info: dict):
        """
        Insert or update bot user information in analytics.bot_users.

        Args:
            user_info: Dict with keys: slack_user_id, slack_username, real_name,
                      email, display_name, is_admin, is_bot
        """
        sql = """
            INSERT INTO analytics.bot_users (
                slack_user_id, slack_username, real_name, email,
                display_name, is_admin, is_bot, first_seen_at, last_seen_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (slack_user_id)
            DO UPDATE SET
                slack_username = EXCLUDED.slack_username,
                real_name = EXCLUDED.real_name,
                email = EXCLUDED.email,
                display_name = EXCLUDED.display_name,
                last_seen_at = NOW(),
                total_interactions = bot_users.total_interactions + 1,
                updated_at = NOW()
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        user_info.get('slack_user_id'),
                        user_info.get('slack_username'),
                        user_info.get('real_name'),
                        user_info.get('email'),
                        user_info.get('display_name'),
                        user_info.get('is_admin', False),
                        user_info.get('is_bot', False)
                    ))
                    conn.commit()
                    logger.debug("User logged to analytics.bot_users: %s", user_info.get('slack_user_id'))
        except Exception as e:
            logger.error("Failed to log user to analytics: %s", str(e))

    def save_conversation_state(self, user_id: str, channel_id: str,
                                state: str, last_query: str = None,
                                last_sql_query: str = None, query_type: str = None):
        """
        Save or update conversation state for persistence across restarts.

        Args:
            user_id: Slack user ID
            channel_id: Slack channel ID
            state: Current conversation state (initial, waiting_for_confirmation, etc.)
            last_query: Last user query text
            last_sql_query: Last generated SQL query
            query_type: Query type (informational, data_extraction)
        """
        sql = """
            INSERT INTO analytics.bot_conversation_state
                (slack_user_id, channel_id, state, last_query, last_sql_query, last_query_type, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (slack_user_id, channel_id)
            DO UPDATE SET
                state = EXCLUDED.state,
                last_query = EXCLUDED.last_query,
                last_sql_query = EXCLUDED.last_sql_query,
                last_query_type = EXCLUDED.last_query_type,
                updated_at = NOW()
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (user_id, channel_id, state, last_query, last_sql_query, query_type))
                    conn.commit()
                    logger.debug("Conversation state saved: user=%s, state=%s", user_id, state)
        except Exception as e:
            logger.error("Failed to save conversation state: %s", str(e))

    def load_conversation_state(self, user_id: str, channel_id: str) -> dict:
        """
        Load conversation state from DB if not expired (30 min timeout).

        Args:
            user_id: Slack user ID
            channel_id: Slack channel ID

        Returns:
            Dict with state, last_query, last_sql_query, last_query_type or None if expired/missing
        """
        sql = """
            SELECT state, last_query, last_sql_query, last_query_type, updated_at
            FROM analytics.bot_conversation_state
            WHERE slack_user_id = %s AND channel_id = %s
              AND updated_at > NOW() - INTERVAL '30 minutes'
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (user_id, channel_id))
                    row = cur.fetchone()
                    if row:
                        return {
                            "state": row[0],
                            "last_query": row[1],
                            "last_sql_query": row[2],
                            "last_query_type": row[3],
                            "updated_at": row[4]
                        }
                    return None
        except Exception as e:
            logger.error("Failed to load conversation state: %s", str(e))
            return None

    def get_recent_interactions(self, user_id: str, channel_id: str,
                                limit: int = 5, minutes: int = 30) -> list:
        """
        Get recent conversation interactions for multi-turn context.

        Args:
            user_id: Slack user ID
            channel_id: Slack channel ID
            limit: Max number of interactions to return
            minutes: Time window in minutes

        Returns:
            List of dicts with user_message, bot_response, sql_query, query_type, created_at
            Ordered oldest-first for chronological context.
        """
        sql = """
            SELECT user_message, bot_response, sql_query, query_type, created_at
            FROM analytics.bot_interactions
            WHERE slack_user_id = %s AND channel_id = %s
              AND created_at > NOW() - INTERVAL '%s minutes'
            ORDER BY created_at DESC
            LIMIT %s
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (user_id, channel_id, minutes, limit))
                    rows = cur.fetchall()
                    results = [
                        {
                            "user_message": row[0],
                            "bot_response": row[1],
                            "sql_query": row[2],
                            "query_type": row[3],
                            "created_at": row[4]
                        }
                        for row in rows
                    ]
                    # Reverse to get oldest-first (chronological order)
                    results.reverse()
                    return results
        except Exception as e:
            logger.error("Failed to get recent interactions: %s", str(e))
            return []

    def find_similar_cached_query(self, user_message: str, limit: int = 3) -> list:
        """
        Find similar successful queries using PostgreSQL full-text search on bot_query_patterns.

        Args:
            user_message: Current user query
            limit: Max number of similar queries to return

        Returns:
            List of dicts with user_message and sql_query from past successes
        """
        sql = """
            SELECT question_text, sql_query, row_count,
                   ts_rank(to_tsvector('russian', question_text),
                           plainto_tsquery('russian', %s)) AS rank
            FROM analytics.bot_query_patterns
            WHERE was_successful = true
              AND user_feedback IS DISTINCT FROM 'negative'
              AND to_tsvector('russian', question_text) @@ plainto_tsquery('russian', %s)
            ORDER BY rank DESC
            LIMIT %s
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (user_message, user_message, limit))
                    rows = cur.fetchall()

            return [{"user_message": row[0], "sql_query": row[1]} for row in rows]

        except Exception as e:
            logger.error("Failed to find cached queries: %s", str(e))
            return []

    def save_query_pattern(self, question: str, sql_query: str, row_count: int, created_by: str = "bot"):
        """
        Save a successful query pattern to bot_query_patterns.

        Args:
            question: User's natural language question
            sql_query: The SQL that returned results
            row_count: Number of rows returned
            created_by: Slack user ID or 'bot'
        """
        sql = """
            INSERT INTO analytics.bot_query_patterns
                (question_text, sql_query, row_count, was_successful, created_by)
            VALUES (%s, %s, %s, true, %s)
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (question, sql_query, row_count, created_by))
                    conn.commit()
            logger.info("Saved query pattern: %s", question[:80])
        except Exception as e:
            logger.error("Failed to save query pattern: %s", str(e))

    def mark_pattern_feedback(self, interaction_id: int, feedback: str):
        """
        Update user feedback on a query pattern (positive/negative).

        Args:
            interaction_id: ID in bot_query_patterns
            feedback: 'positive' or 'negative'
        """
        sql = """
            UPDATE analytics.bot_query_patterns
            SET user_feedback = %s
            WHERE id = %s
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (feedback, interaction_id))
                    conn.commit()
            logger.info("Marked pattern %d as %s", interaction_id, feedback)
        except Exception as e:
            logger.error("Failed to mark pattern feedback: %s", str(e))

    def get_latest_pattern_id(self, question: str) -> int:
        """Get the ID of the most recently saved pattern for a question."""
        sql = """
            SELECT id FROM analytics.bot_query_patterns
            WHERE question_text = %s
            ORDER BY created_at DESC LIMIT 1
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (question,))
                    row = cur.fetchone()
                    return row[0] if row else None
        except Exception as e:
            logger.error("Failed to get latest pattern id: %s", str(e))
            return None

    def log_bot_interaction(self, interaction_data: dict):
        """
        Log bot interaction to analytics.bot_interactions.

        Args:
            interaction_data: Dict with keys: session_id, slack_user_id, slack_username,
                             real_name, channel_id, user_message, query_type, bot_response,
                             sql_query, sql_executed, sql_execution_time_ms, rows_returned,
                             error_message, table_generated
        """
        sql = """
            INSERT INTO analytics.bot_interactions (
                session_id, slack_user_id, slack_username, real_name, channel_id,
                user_message, query_type, bot_response, sql_query, sql_executed,
                sql_execution_time_ms, rows_returned, error_message, table_generated,
                table_generated_ts, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        interaction_data.get('session_id'),
                        interaction_data.get('slack_user_id'),
                        interaction_data.get('slack_username'),
                        interaction_data.get('real_name'),
                        interaction_data.get('channel_id'),
                        interaction_data.get('user_message'),
                        interaction_data.get('query_type'),
                        interaction_data.get('bot_response'),
                        interaction_data.get('sql_query'),
                        interaction_data.get('sql_executed', False),
                        interaction_data.get('sql_execution_time_ms'),
                        interaction_data.get('rows_returned'),
                        interaction_data.get('error_message'),
                        interaction_data.get('table_generated', False),
                        interaction_data.get('table_generated_ts')
                    ))
                    conn.commit()
                    logger.debug("Interaction logged to analytics.bot_interactions")
        except Exception as e:
            logger.error("Failed to log interaction to analytics: %s", str(e))
