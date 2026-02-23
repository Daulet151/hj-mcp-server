"""
Slack Bot for Hero's Journey SQL Assistant
Multi-agent system: Classifier -> Informational/Analytical -> Excel Generation
"""
import json
import threading
import time
from datetime import datetime
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

sql_generator = SQLGenerator(Config.ANTHROPIC_API_KEY, Config.ANTHROPIC_MODEL)
sql_generator.set_schema(schema_docs)

db_manager = DatabaseManager(
    host=Config.DB_HOST,
    dbname=Config.DB_NAME,
    user=Config.DB_USER,
    password=Config.DB_PASSWORD,
    port=Config.DB_PORT
)

# Enable SQL caching: inject db_manager so sql_generator can use past successful queries
sql_generator.db_manager = db_manager

# Load all live tables from DB into the system prompt
sql_generator.load_live_tables()

excel_generator = ExcelGenerator()

# Initialize multi-agent orchestrator
# Pass sql_generator and db_manager to analytical agent for real data analysis
orchestrator = AgentOrchestrator(
    api_key=Config.ANTHROPIC_API_KEY,
    schema_docs=schema_docs,
    sql_generator=sql_generator,
    db_manager=db_manager,
    model=Config.ANTHROPIC_MODEL
)

# Test database connection on startup
if not db_manager.test_connection():
    logger.error("Failed to connect to database. Please check your configuration.")
else:
    logger.info("Database connection successful")

logger.info("Multi-agent system initialized successfully")


def get_slack_user_info(user_id: str) -> dict:
    """
    Fetch user information from Slack API using users.list.

    Args:
        user_id: Slack user ID

    Returns:
        Dict with user information
    """
    try:
        # Use users.list instead of users.info (workaround for user_not_found issue)
        response = requests.post(
            "https://slack.com/api/users.list",
            headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}"},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if not data.get('ok'):
            logger.error("Failed to fetch users list: %s", data.get('error'))
            return {
                'slack_user_id': user_id,
                'slack_username': 'unknown',
                'real_name': 'unknown',
                'email': None,
                'display_name': 'unknown',
                'is_admin': False,
                'is_bot': False
            }

        # Find user in the list
        members = data.get('members', [])
        for user in members:
            if user.get('id') == user_id:
                profile = user.get('profile', {})
                return {
                    'slack_user_id': user_id,
                    'slack_username': user.get('name', 'unknown'),
                    'real_name': user.get('real_name', 'unknown'),
                    'email': profile.get('email'),
                    'display_name': profile.get('display_name', user.get('name', 'unknown')),
                    'is_admin': user.get('is_admin', False),
                    'is_bot': user.get('is_bot', False)
                }

        # User not found in list
        logger.warning("User %s not found in workspace members list", user_id)
        return {
            'slack_user_id': user_id,
            'slack_username': 'unknown',
            'real_name': 'unknown',
            'email': None,
            'display_name': 'unknown',
            'is_admin': False,
            'is_bot': False
        }

    except Exception as e:
        logger.error("Error fetching user info: %s", str(e))
        return {
            'slack_user_id': user_id,
            'slack_username': 'unknown',
            'real_name': 'unknown',
            'email': None,
            'display_name': 'unknown',
            'is_admin': False,
            'is_bot': False
        }


def process_slack_query(user_prompt: str, channel_id: str, user_id: str, thread_ts: str = None):
    """
    Process user query using multi-agent system.

    Args:
        user_prompt: Natural language question from user
        channel_id: Slack channel ID to send response
        user_id: Slack user ID
    """
    # Get user info and log to analytics
    user_info = get_slack_user_info(user_id)
    db_manager.log_bot_user(user_info)

    # Generate session ID for tracking
    session_id = f"{user_id}_{channel_id}_{datetime.now().strftime('%Y%m%d')}"
    start_time = time.time()

    # Send typing indicator immediately
    typing_message_ts = post_slack_typing_indicator(channel_id, thread_ts)

    # Initialize interaction data
    interaction_data = {
        'session_id': session_id,
        'slack_user_id': user_id,
        'slack_username': user_info.get('slack_username'),
        'real_name': user_info.get('real_name'),
        'channel_id': channel_id,
        'user_message': user_prompt,
        'query_type': None,
        'bot_response': None,
        'sql_query': None,
        'sql_executed': False,
        'sql_execution_time_ms': None,
        'rows_returned': None,
        'error_message': None,
        'table_generated': False,
        'table_generated_ts': None
    }

    try:
        logger.info("Processing query from user %s in channel %s", user_id, channel_id)

        # Process message through orchestrator
        response_text, should_generate_table, data_context, original_query, query_type = orchestrator.process_message(
            user_message=user_prompt,
            user_id=user_id,
            channel_id=channel_id
        )

        # Update interaction data
        interaction_data['query_type'] = query_type
        interaction_data['bot_response'] = response_text

        # Update typing indicator with agent's response
        if typing_message_ts:
            update_slack_message(channel_id, typing_message_ts, response_text)
        else:
            # Fallback: send as new message if typing indicator failed
            post_slack_text_message(channel_id, response_text, thread_ts)

        # If should generate table, proceed with Excel generation
        if should_generate_table:
            sql_start_time = time.time()

            # Check if we have cached data from analysis
            if data_context and data_context.get("dataframe") is not None:
                # Use cached results from analytical agent
                logger.info("Using cached data from analysis")
                df = data_context["dataframe"]
                sql_query = data_context["sql_query"]

                # Update interaction data
                interaction_data['sql_query'] = sql_query
                interaction_data['sql_executed'] = True
                interaction_data['sql_execution_time_ms'] = int((time.time() - sql_start_time) * 1000)
                interaction_data['rows_returned'] = len(df)
            else:
                # Fallback: generate SQL and execute (shouldn't happen normally)
                logger.info("No cached data, generating fresh query")
                if not original_query:
                    logger.error("No original query available for table generation")
                    interaction_data['error_message'] = "No original query available"
                    db_manager.log_bot_interaction(interaction_data)
                    post_slack_error(channel_id, "Не удалось получить оригинальный запрос")
                    return

                logger.info("Generating table for query: %s", original_query[:100])
                sql_query = sql_generator.generate_query(original_query)
                df = db_manager.execute_query(sql_query)

                # Update interaction data
                interaction_data['sql_query'] = sql_query
                interaction_data['sql_executed'] = True
                interaction_data['sql_execution_time_ms'] = int((time.time() - sql_start_time) * 1000)
                interaction_data['rows_returned'] = len(df)

            # Process results
            try:

                if excel_generator.dataframe_is_empty(df):
                    result = "Запрос выполнен успешно, но не вернул данных (результат пуст)."
                    post_slack_message_and_file(channel_id, sql_query, result, thread_ts=thread_ts)

                    # Log interaction
                    db_manager.log_bot_interaction(interaction_data)
                else:
                    # Create Excel file
                    excel_buffer = excel_generator.create_excel_buffer(df)

                    # Send to Slack
                    post_slack_message_and_file(channel_id, sql_query, excel_buffer, thread_ts=thread_ts)

                    # Update and log interaction
                    interaction_data['table_generated'] = True
                    interaction_data['table_generated_ts'] = datetime.now()
                    db_manager.log_bot_interaction(interaction_data)

            except Exception as db_error:
                error_msg = f"Ошибка выполнения SQL-запроса: {str(db_error)}"
                logger.error(error_msg)

                # Log error
                interaction_data['error_message'] = str(db_error)
                db_manager.log_bot_interaction(interaction_data)

                post_slack_message_and_file(channel_id, sql_query, error_msg, thread_ts=thread_ts)
        else:
            # No table generation - just log the interaction
            db_manager.log_bot_interaction(interaction_data)

    except Exception as e:
        error_msg = f"⚠️ Ошибка при обработке запроса: {str(e)}"
        logger.error(error_msg)

        # Log error to analytics
        interaction_data['error_message'] = str(e)
        db_manager.log_bot_interaction(interaction_data)

        # Update typing indicator with error or send as new message
        if typing_message_ts:
            update_slack_message(channel_id, typing_message_ts, f"*{error_msg}*")
        else:
            post_slack_error(channel_id, error_msg, thread_ts)


def post_slack_message_and_file(channel_id: str, sql_query: str, file_buffer_or_error, filename: str = "query_result.xlsx", thread_ts: str = None):
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
    if thread_ts:
        message_payload["thread_ts"] = thread_ts

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
            complete_payload = {
                "files": [{"id": file_id, "title": filename}],
                "channel_id": channel_id,
                "initial_comment": "*✅ Результат запроса в прикрепленном Excel-файле!*",
            }
            if thread_ts:
                complete_payload["thread_ts"] = thread_ts

            complete_response = requests.post(
                "https://slack.com/api/files.completeUploadExternal",
                headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}", "Content-Type": "application/json"},
                data=json.dumps(complete_payload),
                timeout=10
            ).json()

            if complete_response.get('ok'):
                logger.info("Excel file uploaded to Slack successfully")
            else:
                logger.error("Failed to complete upload: %s", complete_response.get('error'))

        except Exception as e:
            logger.error("Failed to upload file to Slack: %s", str(e))


def post_slack_typing_indicator(channel_id: str, thread_ts: str = None) -> str:
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
        typing_payload = {
            "channel": channel_id,
            "text": "🤖 _AI Data Analyst анализирует данные..._",
            "mrkdwn": True
        }
        if thread_ts:
            typing_payload["thread_ts"] = thread_ts

        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}",
                "Content-Type": "application/json"
            },
            data=json.dumps(typing_payload),
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


def post_slack_text_message(channel_id: str, text: str, thread_ts: str = None):
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
        text_payload = {"channel": channel_id, "text": text, "mrkdwn": True}
        if thread_ts:
            text_payload["thread_ts"] = thread_ts

        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}",
                "Content-Type": "application/json"
            },
            data=json.dumps(text_payload),
            timeout=10
        )
        response.raise_for_status()
        logger.debug("Text message sent to Slack")
    except Exception as e:
        logger.error("Failed to send text message to Slack: %s", str(e))


def post_slack_error(channel_id: str, error_message: str, thread_ts: str = None):
    """Send error message to Slack."""
    if not Config.SLACK_BOT_TOKEN:
        return

    try:
        error_payload = {
            "channel": channel_id,
            "text": f"*⚠️ Ошибка:*\n`{error_message}`"
        }
        if thread_ts:
            error_payload["thread_ts"] = thread_ts

        requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}", "Content-Type": "application/json"},
            data=json.dumps(error_payload),
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
        thread_ts = event.get('thread_ts') or event.get('ts')

        if not user_prompt:
            return "OK", 200

        logger.info("Received message from user %s: %s", user_id, user_prompt[:100])

        # Process in background thread to avoid Slack timeout
        thread = threading.Thread(
            target=process_slack_query,
            args=(user_prompt, channel_id, user_id, thread_ts),
            daemon=True
        )
        thread.start()

        # Immediately respond to Slack
        return "OK", 200

    # Handle emoji reactions (👍/👎) for query pattern feedback
    if event_type == 'reaction_added':
        reaction = event.get('reaction', '')
        user_id = event.get('user', '')
        item = event.get('item', {})

        if reaction in ('+1', 'thumbsup', '-1', 'thumbsdown') and item.get('type') == 'message':
            feedback = 'positive' if reaction in ('+1', 'thumbsup') else 'negative'
            channel_id = item.get('channel')

            thread = threading.Thread(
                target=_handle_reaction_feedback,
                args=(channel_id, feedback, user_id),
                daemon=True
            )
            thread.start()

    return "OK", 200


def _handle_reaction_feedback(channel_id: str, feedback: str, user_id: str):
    """
    Handle 👍/👎 reaction on bot message — update query pattern feedback.
    Looks up the most recent pattern saved around the time of that message.
    """
    try:
        # Find the most recent pattern created by this channel around message time
        sql = """
            SELECT id FROM analytics.bot_query_patterns
            WHERE created_by = %s OR created_by = 'bot'
            ORDER BY created_at DESC
            LIMIT 1
        """
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_id,))
                row = cur.fetchone()
                if row:
                    pattern_id = row[0]
                    db_manager.mark_pattern_feedback(pattern_id, feedback)
                    logger.info("User %s marked pattern %d as %s", user_id, pattern_id, feedback)

                    emoji = "✅" if feedback == 'positive' else "❌"
                    msg = f"{emoji} Спасибо за оценку! Запомню этот паттерн как {'успешный' if feedback == 'positive' else 'неудачный'}."
                    requests.post(
                        "https://slack.com/api/chat.postMessage",
                        headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}", "Content-Type": "application/json"},
                        json={"channel": channel_id, "text": msg},
                        timeout=10
                    )
    except Exception as e:
        logger.error("Failed to handle reaction feedback: %s", str(e))


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
