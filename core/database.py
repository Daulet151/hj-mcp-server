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
