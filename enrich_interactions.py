"""
Enrich historical bot_interactions with user info from bot_users table.
"""
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

print("Updating bot_interactions with user info from bot_users...")

# Update interactions with user info
sql = """
    UPDATE analytics.bot_interactions i
    SET
        slack_username = u.slack_username,
        real_name = u.real_name
    FROM analytics.bot_users u
    WHERE i.slack_user_id = u.slack_user_id
      AND (i.slack_username IS NULL OR i.real_name IS NULL)
"""

try:
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows_updated = cur.rowcount
            conn.commit()
            print(f"Updated {rows_updated} interaction records with user info")
except Exception as e:
    print(f"Error: {e}")

# Verify results
print("\nVerifying update...")
result = db.execute_query("""
    SELECT
        COUNT(*) as total,
        COUNT(slack_username) as with_username,
        COUNT(real_name) as with_real_name,
        COUNT(user_message) as with_message,
        COUNT(sql_query) as with_sql
    FROM analytics.bot_interactions
""")

print("\nStatistics:")
print(f"  Total interactions: {result.iloc[0]['total']}")
print(f"  With username: {result.iloc[0]['with_username']}")
print(f"  With real name: {result.iloc[0]['with_real_name']}")
print(f"  With user message: {result.iloc[0]['with_message']}")
print(f"  With SQL query: {result.iloc[0]['with_sql']}")

print("\nDone!")
