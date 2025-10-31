"""
Slack Bot for Hero's Journey SQL Assistant
Processes natural language queries and returns Excel results in Slack.
"""
import json
import threading
from flask import Flask, request, jsonify
import requests

from config import Config
from core import SchemaLoader, SQLGenerator, DatabaseManager, ExcelGenerator
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

# Test database connection on startup
if not db_manager.test_connection():
    logger.error("Failed to connect to database. Please check your configuration.")
else:
    logger.info("Database connection successful")


def process_slack_query(user_prompt: str, channel_id: str):
    """
    Process user query in background thread.

    Args:
        user_prompt: Natural language question from user
        channel_id: Slack channel ID to send response
    """
    try:
        logger.info("Processing query from channel %s", channel_id)

        # 1. Generate SQL query
        sql_query = sql_generator.generate_query(user_prompt)

        # 2. Execute query and get results
        try:
            df = db_manager.execute_query(sql_query)

            if excel_generator.dataframe_is_empty(df):
                result = "Запрос выполнен успешно, но не вернул данных (результат пуст)."
                post_slack_message_and_file(channel_id, sql_query, result)
            else:
                # 3. Create Excel file
                excel_buffer = excel_generator.create_excel_buffer(df)

                # 4. Send to Slack
                post_slack_message_and_file(channel_id, sql_query, excel_buffer)

        except Exception as db_error:
            error_msg = f"Ошибка выполнения SQL-запроса: {str(db_error)}"
            logger.error(error_msg)
            post_slack_message_and_file(channel_id, sql_query, error_msg)

    except Exception as e:
        error_msg = f"Ошибка при обработке запроса: {str(e)}"
        logger.error(error_msg)
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

        if not user_prompt:
            return "OK", 200

        logger.info("Received message: %s", user_prompt[:100])

        # Process in background thread to avoid Slack timeout
        thread = threading.Thread(
            target=process_slack_query,
            args=(user_prompt, channel_id),
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
