"""
Import historical bot queries from logs into analytics.bot_interactions table.
"""
import re
from datetime import datetime
from core.database import DatabaseManager
from config import Config

# Initialize database
db = DatabaseManager(
    host=Config.DB_HOST,
    dbname=Config.DB_NAME,
    user=Config.DB_USER,
    password=Config.DB_PASSWORD,
    port=Config.DB_PORT
)

# Read downloaded log file
log_file = r'C:\Users\daule\Downloads\bot_queries.log'

# Parse pattern: Dec 01 06:56:54 ... Processing query from user U08NW5WKP37 in channel D09LB0D10KG
pattern = r'(\w+ \d+ \d+:\d+:\d+).*Processing query from user ([A-Z0-9]+) in channel ([A-Z0-9]+)'

interactions = []

print("Parsing log file...")
with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        match = re.search(pattern, line)
        if match:
            timestamp_str = match.group(1)
            user_id = match.group(2)
            channel_id = match.group(3)

            # Parse timestamp (add current year)
            try:
                year = datetime.now().year
                timestamp = datetime.strptime(f'{year} {timestamp_str}', '%Y %b %d %H:%M:%S')
            except Exception as e:
                print(f"Error parsing timestamp '{timestamp_str}': {e}")
                timestamp = datetime.now()

            # Create session_id
            session_id = f"{user_id}_{channel_id}_{timestamp.strftime('%Y%m%d')}"

            interactions.append({
                'session_id': session_id,
                'slack_user_id': user_id,
                'channel_id': channel_id,
                'created_at': timestamp
            })

print(f"Found {len(interactions)} historical interactions")

# Get unique user IDs
unique_users = set([i['slack_user_id'] for i in interactions])
print(f"Found {len(unique_users)} unique users")

# First, create users in bot_users table (without FK constraint issues)
print("\nCreating users in bot_users table...")
user_sql = """
    INSERT INTO analytics.bot_users (
        slack_user_id, slack_username, real_name, first_seen_at
    ) VALUES (%s, %s, %s, %s)
    ON CONFLICT (slack_user_id) DO NOTHING
"""

for user_id in unique_users:
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(user_sql, (user_id, 'historical', 'Historical User', interactions[0]['created_at']))
                conn.commit()
    except Exception as e:
        print(f"Error creating user {user_id}: {e}")

# Now insert interactions
sql = """
    INSERT INTO analytics.bot_interactions (
        session_id, slack_user_id, channel_id, created_at
    ) VALUES (%s, %s, %s, %s)
"""

inserted = 0
skipped = 0

print("\nInserting interactions into database...")
for interaction in interactions:
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    interaction['session_id'],
                    interaction['slack_user_id'],
                    interaction['channel_id'],
                    interaction['created_at']
                ))
                conn.commit()
                inserted += 1
    except Exception as e:
        # Skip duplicates or errors
        skipped += 1
        if 'duplicate' not in str(e).lower():
            print(f"Error: {e}")

print(f"\n=== Results ===")
print(f"Total parsed: {len(interactions)}")
print(f"Successfully inserted: {inserted}")
print(f"Skipped/duplicates: {skipped}")
print("\nDone!")
