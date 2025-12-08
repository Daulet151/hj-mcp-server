"""
Fetch message history from Slack channels to recover user_message data.
"""
import requests
import sys
from datetime import datetime
from core.database import DatabaseManager
from config import Config

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

# Initialize database
db = DatabaseManager(
    host=Config.DB_HOST,
    dbname=Config.DB_NAME,
    user=Config.DB_USER,
    password=Config.DB_PASSWORD,
    port=Config.DB_PORT
)

# First, test Slack API token and scopes
print("Testing Slack API token and scopes...")
test_response = requests.post(
    "https://slack.com/api/auth.test",
    headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}"},
    timeout=10
)
test_data = test_response.json()
if test_data.get('ok'):
    print(f"[OK] Token valid for workspace: {test_data.get('team')}")
    print(f"[OK] Bot user: {test_data.get('user')}")
else:
    print(f"[ERROR] Token invalid: {test_data.get('error')}")
    sys.exit(1)

# Get all historical interactions that need user_message
print("\nQuerying database for interactions without user_message...")
result = db.execute_query("""
    SELECT
        id,
        slack_user_id,
        channel_id,
        created_at,
        user_message
    FROM analytics.bot_interactions
    WHERE user_message IS NULL
    ORDER BY created_at
""")

print(f"Found {len(result)} interactions without user_message")
print("\nFetching Slack message history...\n")
sys.stdout.flush()

updated_count = 0
error_count = 0
not_found_count = 0

for idx, row in result.iterrows():
    interaction_id = row['id']
    user_id = row['slack_user_id']
    channel_id = row['channel_id']
    created_at = row['created_at']

    # Convert timestamp to Slack format (Unix timestamp)
    ts_start = int(created_at.timestamp()) - 5  # 5 seconds before
    ts_end = int(created_at.timestamp()) + 5    # 5 seconds after

    print(f"[{idx+1}/{len(result)}] [{interaction_id}] Channel {channel_id}, User {user_id}, Time {created_at}")
    sys.stdout.flush()

    try:
        # Fetch conversation history
        response = requests.post(
            "https://slack.com/api/conversations.history",
            headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}"},
            json={
                "channel": channel_id,
                "oldest": str(ts_start),
                "latest": str(ts_end),
                "limit": 10
            },
            timeout=10
        )

        data = response.json()

        if not data.get('ok'):
            error = data.get('error')
            print(f"  [ERROR] API error: {error}")
            if error == 'missing_scope':
                print(f"  [INFO] Need scope: channels:history, groups:history, im:history, mpim:history")
            error_count += 1
            sys.stdout.flush()
            continue

        messages = data.get('messages', [])
        print(f"  Found {len(messages)} messages in time range")
        sys.stdout.flush()

        # Find message from this user
        user_message = None
        for msg in messages:
            if msg.get('user') == user_id and msg.get('text'):
                user_message = msg.get('text')
                print(f"  [OK] Found message (length: {len(user_message)})")
                sys.stdout.flush()
                break

        if user_message:
            # Update database
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE analytics.bot_interactions SET user_message = %s WHERE id = %s",
                        (user_message, interaction_id)
                    )
                    conn.commit()
            print(f"  [OK] Updated DB")
            updated_count += 1
            sys.stdout.flush()
        else:
            print(f"  [WARN] No message from this user")
            not_found_count += 1
            sys.stdout.flush()

    except Exception as e:
        print(f"  [ERROR] Exception: {e}")
        error_count += 1
        sys.stdout.flush()

print(f"\n=== Summary ===")
print(f"Total processed: {len(result)}")
print(f"Successfully updated: {updated_count}")
print(f"Not found: {not_found_count}")
print(f"Errors: {error_count}")
print("\nDone!")
