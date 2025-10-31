"""
Excel file generation from query results.
"""
import io
import pandas as pd
from typing import Union
from utils.logger import setup_logger

logger = setup_logger(__name__)


class ExcelGenerator:
    """Generates Excel files from pandas DataFrames."""

    @staticmethod
    def create_excel_buffer(df: pd.DataFrame, sheet_name: str = "Результат") -> io.BytesIO:
        """
        Create Excel file in memory from DataFrame.

        Args:
            df: pandas DataFrame with data
            sheet_name: Name for the Excel sheet

        Returns:
            BytesIO buffer containing Excel file

        Raises:
            Exception: If Excel creation fails
        """
        logger.info("Creating Excel file with %d rows, %d columns", len(df), len(df.columns))

        try:
            # Create buffer in memory
            excel_buffer = io.BytesIO()

            # Write DataFrame to Excel
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name=sheet_name)

            # Reset buffer position
            excel_buffer.seek(0)

            logger.info("Excel file created successfully")
            return excel_buffer

        except Exception as e:
            logger.error("Failed to create Excel file: %s", str(e))
            raise

    @staticmethod
    def dataframe_is_empty(df: pd.DataFrame) -> bool:
        """Check if DataFrame is empty."""
        return df is None or df.empty

    @staticmethod
    def get_summary(df: pd.DataFrame) -> str:
        """
        Get summary information about DataFrame.

        Args:
            df: pandas DataFrame

        Returns:
            Summary string
        """
        if ExcelGenerator.dataframe_is_empty(df):
            return "No data"

        return f"{len(df)} rows × {len(df.columns)} columns"
