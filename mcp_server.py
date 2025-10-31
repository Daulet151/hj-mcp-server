"""
MCP Server for Hero's Journey SQL Assistant
Exposes database querying capabilities via Model Context Protocol.
Returns results as text tables only (no Excel) for optimal performance.
"""
import asyncio
from typing import Any
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp import types

from config import Config
from core import SchemaLoader, SQLGenerator, DatabaseManager
from utils.logger import setup_logger

# Setup logging
logger = setup_logger(__name__, Config.LOG_LEVEL)

# Validate configuration
try:
    Config.validate()
    logger.info("MCP Server configuration validated")
except ValueError as e:
    logger.error("Configuration error: %s", str(e))
    raise

# Initialize core components
schema_loader = SchemaLoader(Config.DOCS_DIR)
schema_docs = schema_loader.load_all()

sql_generator = SQLGenerator(Config.OPENAI_API_KEY, Config.OPENAI_MODEL)
sql_generator.set_schema(schema_docs)

db_manager = DatabaseManager(
    host=Config.DB_HOST,
    dbname=Config.DB_NAME,
    user=Config.DB_USER,
    password=Config.DB_PASSWORD,
    port=Config.DB_PORT
)

# Initialize MCP server
server = Server(Config.MCP_SERVER_NAME)

logger.info("MCP Server initialized: %s v%s", Config.MCP_SERVER_NAME, Config.MCP_SERVER_VERSION)


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.

    Returns list of tools that can query the Hero's Journey database.
    """
    return [
        types.Tool(
            name="query_database",
            description="""Query the Hero's Journey database using natural language.

            This tool accepts questions in Russian or English and:
            1. Generates optimized SQL query
            2. Executes query against PostgreSQL database
            3. Returns results as formatted text table (fast and efficient)

            Available data:
            - User subscriptions (heropass)
            - Marathon participation (usermarathonevent)
            - Bookings and check-ins
            - Payments
            - Notifications

            Examples:
            - "Show users whose subscription expires in the next 7 days"
            - "How many users completed Hero's Week marathon?"
            - "List all payments for Burn I program"

            Note: For Excel exports, use the Slack bot instead.
            """,
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural language question about Hero's Journey data (Russian or English)"
                    }
                },
                "required": ["question"]
            }
        ),
        types.Tool(
            name="execute_sql",
            description="""Execute a specific SQL SELECT query against Hero's Journey database.

            Use this when you already have a SQL query and want to execute it directly.
            Only SELECT queries are allowed. The query must use olap_schema prefix for tables.

            Returns query results as formatted text table.

            Note: For Excel exports, use the Slack bot instead.
            """,
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "SQL SELECT query to execute (must start with SELECT)"
                    }
                },
                "required": ["sql"]
            }
        ),
        types.Tool(
            name="get_schema_info",
            description="""Get information about available database tables and their structure.

            Returns documentation about:
            - Available tables in the database
            - Column names and types
            - Business terms and their meanings
            - Relationships between tables

            Use this to understand what data is available before querying.
            """,
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Optional: specific table name to get detailed info. If not provided, lists all tables."
                    }
                }
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict[str, Any] | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    """
    try:
        if name == "query_database":
            return await query_database_tool(arguments or {})
        elif name == "execute_sql":
            return await execute_sql_tool(arguments or {})
        elif name == "get_schema_info":
            return await get_schema_info_tool(arguments or {})
        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        logger.error("Tool execution error: %s", str(e))
        return [types.TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


async def query_database_tool(arguments: dict) -> list[types.TextContent]:
    """Handle natural language database queries - returns text table only."""
    question = arguments.get("question", "")

    if not question:
        raise ValueError("Question is required")

    logger.info("Processing natural language query: %s", question[:100])

    # Generate SQL
    sql_query = sql_generator.generate_query(question)
    logger.info("Generated SQL query")

    # Execute query
    df = db_manager.execute_query(sql_query)

    # Format response
    result_text = f"**Generated SQL:**\n```sql\n{sql_query}\n```\n\n"

    # Check if DataFrame is empty
    if df is None or df.empty:
        result_text += "**Result:** No data returned (query executed successfully but returned empty result)"
        return [types.TextContent(type="text", text=result_text)]

    result_text += f"**Result:** {len(df)} rows × {len(df.columns)} columns\n\n"

    # Return as formatted table (ALWAYS)
    max_display_rows = 200  # Увеличили лимит для текстовых таблиц
    result_text += "```\n" + df.to_string(index=False, max_rows=max_display_rows) + "\n```"

    if len(df) > max_display_rows:
        result_text += f"\n\n*(Showing first {max_display_rows} of {len(df)} rows. For full dataset, use Slack bot.)*"

    return [types.TextContent(type="text", text=result_text)]


async def execute_sql_tool(arguments: dict) -> list[types.TextContent]:
    """Handle direct SQL execution - returns text table only."""
    sql = arguments.get("sql", "")

    if not sql:
        raise ValueError("SQL query is required")

    # Validate it's a SELECT query
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    logger.info("Executing SQL query: %s", sql[:100])

    # Execute query
    df = db_manager.execute_query(sql)

    # Format response
    result_text = f"**Executed SQL:**\n```sql\n{sql}\n```\n\n"

    # Check if DataFrame is empty
    if df is None or df.empty:
        result_text += "**Result:** No data returned"
        return [types.TextContent(type="text", text=result_text)]

    result_text += f"**Result:** {len(df)} rows × {len(df.columns)} columns\n\n"

    # Return as table (ALWAYS)
    max_display_rows = 200  # Увеличили лимит для текстовых таблиц
    result_text += "```\n" + df.to_string(index=False, max_rows=max_display_rows) + "\n```"

    if len(df) > max_display_rows:
        result_text += f"\n\n*(Showing first {max_display_rows} of {len(df)} rows. For full dataset, use Slack bot.)*"

    return [types.TextContent(type="text", text=result_text)]


async def get_schema_info_tool(arguments: dict) -> list[types.TextContent]:
    """Handle schema information requests."""
    table_name = arguments.get("table_name")

    if table_name:
        # Get specific table info
        table_info = schema_loader.get_table_info(table_name)

        if not table_info:
            return [types.TextContent(
                type="text",
                text=f"Table '{table_name}' not found in schema documentation."
            )]

        result = f"# Table: {table_info.get('table', table_name)}\n\n"
        result += f"**Description:** {table_info.get('description', 'N/A')}\n\n"
        result += "## Columns:\n\n"

        for col in table_info.get('columns', []):
            result += f"- **{col['name']}** ({col['type']}): {col.get('description', '')}\n"
            if 'synonyms_ru' in col:
                result += f"  - Synonyms: {', '.join(col['synonyms_ru'])}\n"

        return [types.TextContent(type="text", text=result)]
    else:
        # List all tables
        tables = schema_loader.get_table_names()

        result = f"# Hero's Journey Database Schema\n\n"
        result += f"**Total tables:** {len(tables)}\n\n"
        result += "## Available Tables:\n\n"

        for table in tables:
            table_info = schema_loader.get_table_info(table)
            result += f"- **{table}**: {table_info.get('description', 'N/A')}\n"

        result += "\n*Use `get_schema_info` with a specific table_name to see detailed column information.*"

        return [types.TextContent(type="text", text=result)]


async def main():
    """Run the MCP server."""
    logger.info("Starting MCP server...")

    # Test database connection
    if not db_manager.test_connection():
        logger.error("Failed to connect to database. Server may not function properly.")
    else:
        logger.info("Database connection successful")

    async with stdio_server() as (read_stream, write_stream):
        logger.info("MCP server running on stdio")
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=Config.MCP_SERVER_NAME,
                server_version=Config.MCP_SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
