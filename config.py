"""
Configuration management for the application.
Loads settings from environment variables with validation.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Application configuration"""

    # Base paths
    BASE_DIR = Path(__file__).parent
    DOCS_DIR = BASE_DIR / "docs"

    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

    # Slack Configuration
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

    # Database Configuration
    DB_HOST = os.getenv("DB_HOST")
    DB_NAME = os.getenv("DB_NAME", "HJ_dwh")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))

    # Application Configuration
    FLASK_PORT = int(os.getenv("FLASK_PORT", "3000"))
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # MCP Server Configuration
    MCP_SERVER_NAME = os.getenv("MCP_SERVER_NAME", "herojourney-sql-assistant")
    MCP_SERVER_VERSION = os.getenv("MCP_SERVER_VERSION", "1.0.0")

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        required = [
            ("OPENAI_API_KEY", cls.OPENAI_API_KEY),
            ("DB_HOST", cls.DB_HOST),
            ("DB_USER", cls.DB_USER),
            ("DB_PASSWORD", cls.DB_PASSWORD),
        ]

        missing = [name for name, value in required if not value]

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Please check your .env file."
            )

        return True

    @classmethod
    def get_db_url(cls):
        """Get database connection URL"""
        return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
