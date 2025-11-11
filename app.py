"""
Slack Bot for Hero's Journey SQL Assistant
Multi-agent system: Classifier -> Informational/Analytical -> Excel Generation
"""
import json
import threading
from flask import Flask, request, jsonify
import requests

from config import Config
from core import SchemaLoader, SQLGenerator, DatabaseManager, ExcelGenerator
from agents import AgentOrchestrator
from utils.logger import setup_logger

# Setup logging
logger = setup_logger(__name__, Config.LOG_LEVEL)

# Validate configuration
try:
    Config.validate()
    logger.info("Configuration validated successfully")
except ValueError as e:
    logger.error("Configuration error: %s", str(e))
    raise

# Initialize Flask app
app = Flask(__name__)

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

excel_generator = ExcelGenerator()

# Initialize multi-agent orchestrator
# Pass sql_generator and db_manager to analytical agent for real data analysis
orchestrator = AgentOrchestrator(
    api_key=Config.OPENAI_API_KEY,
    schema_docs=schema_docs,
    sql_generator=sql_generator,
    db_manager=db_manager,
    model=Config.OPENAI_MODEL
)

# Test database connection on startup
if not db_manager.test_connection():
    logger.error("Failed to connect to database. Please check your configuration.")
else:
    logger.info("Database connection successful")

logger.info("Multi-agent system initialized successfully")


def process_slack_query(user_prompt: str, channel_id: str, user_id: str):
    """
    Process user query using multi-agent system.

    Args:
        user_prompt: Natural language question from user
        channel_id: Slack channel ID to send response
        user_id: Slack user ID
    """
    # Send typing indicator immediately
    typing_message_ts = post_slack_typing_indicator(channel_id)

    try:
        logger.info("Processing query from user %s in channel %s", user_id, channel_id)

        # Process message through orchestrator
        response_text, should_generate_table, data_context, original_query = orchestrator.process_message(
            user_message=user_prompt,
            user_id=user_id,
            channel_id=channel_id
        )

        # Update typing indicator with agent's response
        if typing_message_ts:
            update_slack_message(channel_id, typing_message_ts, response_text)
        else:
            # Fallback: send as new message if typing indicator failed
            post_slack_text_message(channel_id, response_text)

        # If should generate table, proceed with Excel generation
        if should_generate_table:
            # Check if we have cached data from analysis
            if data_context and data_context.get("dataframe") is not None:
                # Use cached results from analytical agent
                logger.info("Using cached data from analysis")
                df = data_context["dataframe"]
                sql_query = data_context["sql_query"]
            else:
                # Fallback: generate SQL and execute (shouldn't happen normally)
                logger.info("No cached data, generating fresh query")
                if not original_query:
                    logger.error("No original query available for table generation")
                    post_slack_error(channel_id, "Не удалось получить оригинальный запрос")
                    return

                logger.info("Generating table for query: %s", original_query[:100])
                sql_query = sql_generator.generate_query(original_query)
                df = db_manager.execute_query(sql_query)

            # Process results
            try:

                if excel_generator.dataframe_is_empty(df):
                    result = "Запрос выполнен успешно, но не вернул данных (результат пуст)."
                    post_slack_message_and_file(channel_id, sql_query, result)
                else:
                    # Create Excel file
                    excel_buffer = excel_generator.create_excel_buffer(df)

                    # Send to Slack
                    post_slack_message_and_file(channel_id, sql_query, excel_buffer)

            except Exception as db_error:
                error_msg = f"Ошибка выполнения SQL-запроса: {str(db_error)}"
                logger.error(error_msg)
                post_slack_message_and_file(channel_id, sql_query, error_msg)

    except Exception as e:
        error_msg = f"⚠️ Ошибка при обработке запроса: {str(e)}"
        logger.error(error_msg)

        # Update typing indicator with error or send as new message
        if typing_message_ts:
            update_slack_message(channel_id, typing_message_ts, f"*{error_msg}*")
        else:
            post_slack_error(channel_id, error_msg)


def post_slack_message_and_file(channel_id: str, sql_query: str, file_buffer_or_error, filename: str = "query_result.xlsx"):
    """
    Send SQL query and Excel file to Slack using new upload protocol.

    Args:
        channel_id: Slack channel ID
        sql_query: Generated SQL query
        file_buffer_or_error: Excel buffer (BytesIO) or error message (str)
        filename: Name for the Excel file
    """
    if not Config.SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not configured, skipping Slack post")
        return

    slack_url_message = "https://slack.com/api/chat.postMessage"
    message_text = f"```{sql_query}\n```"

    # 1. Send SQL query as message
    message_payload = {
        "channel": channel_id,
        "text": "*Сгенерированный SQL-запрос:*",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Сгенерированный SELECT SQL-запрос:*"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": message_text}}
        ]
    }

    try:
        response = requests.post(
            slack_url_message,
            headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}", "Content-Type": "application/json"},
            data=json.dumps(message_payload),
            timeout=10
        )
        response.raise_for_status()
        logger.debug("SQL query sent to Slack")
    except Exception as e:
        logger.error("Failed to send SQL query to Slack: %s", str(e))

    # 2. Handle file or error
    if isinstance(file_buffer_or_error, str):
        # Error message
        error_message = f"*⚠️ Ошибка при получении данных:*\n`{file_buffer_or_error}`"
        try:
            requests.post(
                slack_url_message,
                headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}", "Content-Type": "application/json"},
                data=json.dumps({"channel": channel_id, "text": error_message}),
                timeout=10
            )
        except Exception as e:
            logger.error("Failed to send error to Slack: %s", str(e))
    else:
        # Upload Excel file using new 3-step protocol
        try:
            file_bytes = file_buffer_or_error.getvalue()
            file_length = len(file_bytes)

            # Step 1: Get upload URL
            url_response = requests.post(
                "https://slack.com/api/files.getUploadURLExternal",
                headers={
                    "Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={"length": file_length, "filename": filename},
                timeout=10
            ).json()

            if not url_response.get('ok'):
                logger.error("Failed to get upload URL: %s", url_response.get('error'))
                return

            upload_url = url_response['upload_url']
            file_id = url_response['file_id']

            # Step 2: Upload file
            upload_result = requests.post(
                upload_url,
                headers={"Content-Type": "application/octet-stream"},
                data=file_bytes,
                timeout=30
            )

            if upload_result.status_code != 200:
                logger.error("File upload failed: HTTP %d", upload_result.status_code)
                return

            # Step 3: Complete upload
            complete_response = requests.post(
                "https://slack.com/api/files.completeUploadExternal",
                headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}", "Content-Type": "application/json"},
                data=json.dumps({
                    "files": [{"id": file_id, "title": filename}],
                    "channel_id": channel_id,
                    "initial_comment": "*✅ Результат запроса в прикрепленном Excel-файле!*",
                }),
                timeout=10
            ).json()

            if complete_response.get('ok'):
                logger.info("Excel file uploaded to Slack successfully")
            else:
                logger.error("Failed to complete upload: %s", complete_response.get('error'))

        except Exception as e:
            logger.error("Failed to upload file to Slack: %s", str(e))


def post_slack_typing_indicator(channel_id: str) -> str:
    """
    Send typing indicator message to Slack and return message timestamp.

    Args:
        channel_id: Slack channel ID

    Returns:
        Message timestamp (ts) for later update, or None if failed
    """
    if not Config.SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not configured, skipping Slack post")
        return None

    try:
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}",
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "channel": channel_id,
                "text": "🤖 _AI Data Analyst анализирует данные..._",
                "mrkdwn": True
            }),
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        if result.get('ok'):
            message_ts = result.get('ts')
            logger.debug("Typing indicator sent to Slack (ts: %s)", message_ts)
            return message_ts
        else:
            logger.error("Failed to send typing indicator: %s", result.get('error'))
            return None
    except Exception as e:
        logger.error("Failed to send typing indicator to Slack: %s", str(e))
        return None


def update_slack_message(channel_id: str, message_ts: str, text: str):
    """
    Update existing Slack message with new text.

    Args:
        channel_id: Slack channel ID
        message_ts: Message timestamp to update
        text: New message text (supports markdown)
    """
    if not Config.SLACK_BOT_TOKEN or not message_ts:
        logger.warning("SLACK_BOT_TOKEN not configured or no message_ts, skipping update")
        return

    try:
        response = requests.post(
            "https://slack.com/api/chat.update",
            headers={
                "Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}",
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "channel": channel_id,
                "ts": message_ts,
                "text": text,
                "mrkdwn": True
            }),
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        if result.get('ok'):
            logger.debug("Message updated successfully")
        else:
            logger.error("Failed to update message: %s", result.get('error'))
    except Exception as e:
        logger.error("Failed to update message in Slack: %s", str(e))


def post_slack_text_message(channel_id: str, text: str):
    """
    Send text message to Slack.

    Args:
        channel_id: Slack channel ID
        text: Message text (supports markdown)
    """
    if not Config.SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not configured, skipping Slack post")
        return

    try:
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}",
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "channel": channel_id,
                "text": text,
                "mrkdwn": True
            }),
            timeout=10
        )
        response.raise_for_status()
        logger.debug("Text message sent to Slack")
    except Exception as e:
        logger.error("Failed to send text message to Slack: %s", str(e))


def post_slack_error(channel_id: str, error_message: str):
    """Send error message to Slack."""
    if not Config.SLACK_BOT_TOKEN:
        return

    try:
        requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}", "Content-Type": "application/json"},
            data=json.dumps({
                "channel": channel_id,
                "text": f"*⚠️ Ошибка:*\n`{error_message}`"
            }),
            timeout=10
        )
    except Exception as e:
        logger.error("Failed to send error to Slack: %s", str(e))


@app.route('/slack/events', methods=['POST'])
def slack_events():
    """
    Handle Slack events.
    Processes messages and starts background thread for query processing.
    """
    data = request.json

    # URL verification challenge
    if data and 'challenge' in data:
        logger.info("Responding to Slack URL verification challenge")
        return jsonify({'challenge': data['challenge']})

    # Process message event
    event = data.get('event', {})
    event_type = event.get('type')

    # Only process user messages (not bot messages)
    if event_type == 'message' and 'bot_id' not in event and event.get('subtype') != 'bot_message':

        user_prompt = event.get('text', '').strip()
        channel_id = event.get('channel')
        user_id = event.get('user', 'unknown')

        if not user_prompt:
            return "OK", 200

        logger.info("Received message from user %s: %s", user_id, user_prompt[:100])

        # Process in background thread to avoid Slack timeout
        thread = threading.Thread(
            target=process_slack_query,
            args=(user_prompt, channel_id, user_id),
            daemon=True
        )
        thread.start()

        # Immediately respond to Slack
        return "OK", 200

    return "OK", 200


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "database": db_manager.test_connection(),
        "schema_tables": len(schema_docs["tables"])
    })


if __name__ == '__main__':
    logger.info("Starting Slack Bot on port %d", Config.FLASK_PORT)
    app.run(port=Config.FLASK_PORT, debug=Config.FLASK_DEBUG)
