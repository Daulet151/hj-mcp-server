"""
Enrich historical user data with real names from Slack API.
"""
import requests
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

print("Fetching all users from Slack workspace...")

# Fetch all users from Slack
response = requests.post(
    "https://slack.com/api/users.list",
    headers={"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}"},
    timeout=10
)

data = response.json()

if not data.get('ok'):
    print(f"Error fetching users: {data.get('error')}")
    exit(1)

members = data.get('members', [])
print(f"Found {len(members)} users in Slack workspace")

# Get users from database that need enrichment
result = db.execute_query("""
    SELECT slack_user_id
    FROM analytics.bot_users
    WHERE slack_username = 'historical' OR real_name = 'Historical User'
""")

db_users = result['slack_user_id'].tolist()
print(f"Found {len(db_users)} users in database that need enrichment")

# Enrich each user
updated = 0
not_found = 0

for user_id in db_users:
    # Find user in Slack members
    slack_user = None
    for member in members:
        if member.get('id') == user_id:
            slack_user = member
            break

    if slack_user:
        profile = slack_user.get('profile', {})

        # Update in database
        sql = """
            UPDATE analytics.bot_users
            SET
                slack_username = %s,
                real_name = %s,
                email = %s,
                display_name = %s,
                is_admin = %s,
                is_bot = %s,
                updated_at = NOW()
            WHERE slack_user_id = %s
        """

        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        slack_user.get('name', 'unknown'),
                        slack_user.get('real_name', 'unknown'),
                        profile.get('email'),
                        profile.get('display_name', slack_user.get('name', 'unknown')),
                        slack_user.get('is_admin', False),
                        slack_user.get('is_bot', False),
                        user_id
                    ))
                    conn.commit()
                    updated += 1
                    print(f"[OK] Updated {user_id}: {slack_user.get('real_name')}")
        except Exception as e:
            print(f"[ERROR] Error updating {user_id}: {e}")
    else:
        not_found += 1
        print(f"[WARN] User {user_id} not found in Slack workspace")

print(f"\n=== Results ===")
print(f"Updated: {updated}")
print(f"Not found: {not_found}")
print("\nDone!")
