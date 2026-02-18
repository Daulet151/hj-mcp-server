-- Migration: Add persistent conversation state for multi-turn context
-- Run this on the HJ_dwh database

CREATE TABLE IF NOT EXISTS analytics.bot_conversation_state (
    id SERIAL PRIMARY KEY,
    slack_user_id VARCHAR(50) NOT NULL,
    channel_id VARCHAR(50) NOT NULL,
    state VARCHAR(50) NOT NULL DEFAULT 'initial',
    last_query TEXT,
    last_sql_query TEXT,
    last_query_type VARCHAR(50),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(slack_user_id, channel_id)
);

-- Index for fast history lookup on existing bot_interactions table
CREATE INDEX IF NOT EXISTS idx_bot_interactions_user_channel_time
ON analytics.bot_interactions(slack_user_id, channel_id, created_at DESC);
