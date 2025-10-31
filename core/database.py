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

    def __init__(self, host: str, dbname: str, user: str, password: str, port: int = 5432):
        """
        Initialize database manager.

        Args:
            host: Database host
            dbname: Database name
            user: Database user
            password: Database password
            port: Database port (default: 5432)
        """
        self.config = {
            "host": host,
            "dbname": dbname,
            "user": user,
            "password": password,
            "port": port
        }

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
