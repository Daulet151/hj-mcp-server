-- SQL схема для мониторинга AI Data Analyst бота
-- Создать схему analytics если не существует
CREATE SCHEMA IF NOT EXISTS analytics;

-- Таблица пользователей Slack
CREATE TABLE IF NOT EXISTS analytics.bot_users (
    slack_user_id VARCHAR(50) PRIMARY KEY,
    slack_username VARCHAR(100),
    real_name VARCHAR(200),
    email VARCHAR(200),
    display_name VARCHAR(100),
    is_admin BOOLEAN DEFAULT FALSE,
    is_bot BOOLEAN DEFAULT FALSE,
    first_seen_at TIMESTAMP DEFAULT NOW(),
    last_seen_at TIMESTAMP DEFAULT NOW(),
    total_interactions INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE analytics.bot_users IS 'Пользователи Slack, взаимодействующие с AI Data Analyst ботом';
COMMENT ON COLUMN analytics.bot_users.slack_user_id IS 'Уникальный ID пользователя в Slack';
COMMENT ON COLUMN analytics.bot_users.slack_username IS 'Username пользователя в Slack';
COMMENT ON COLUMN analytics.bot_users.real_name IS 'Реальное имя пользователя';
COMMENT ON COLUMN analytics.bot_users.total_interactions IS 'Общее количество взаимодействий с ботом';

-- Таблица взаимодействий с ботом
CREATE TABLE IF NOT EXISTS analytics.bot_interactions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100),

    -- Информация о пользователе
    slack_user_id VARCHAR(50) REFERENCES analytics.bot_users(slack_user_id),
    slack_username VARCHAR(100),
    real_name VARCHAR(200),
    channel_id VARCHAR(50),

    -- Запрос пользователя
    user_message TEXT,
    user_message_ts TIMESTAMP DEFAULT NOW(),

    -- Классификация
    query_type VARCHAR(50),  -- 'informational', 'data_extraction', or NULL

    -- Ответ бота
    bot_response TEXT,
    bot_response_ts TIMESTAMP DEFAULT NOW(),

    -- SQL и данные (если был data_extraction)
    sql_query TEXT,
    sql_executed BOOLEAN DEFAULT FALSE,
    sql_execution_time_ms INT,
    rows_returned INT,
    error_message TEXT,

    -- Генерация таблицы
    table_generated BOOLEAN DEFAULT FALSE,
    table_generated_ts TIMESTAMP,

    -- Метаданные
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE analytics.bot_interactions IS 'Журнал всех взаимодействий пользователей с AI Data Analyst ботом';
COMMENT ON COLUMN analytics.bot_interactions.session_id IS 'ID сессии: user_id_channel_id_date';
COMMENT ON COLUMN analytics.bot_interactions.query_type IS 'Тип запроса: informational или data_extraction';
COMMENT ON COLUMN analytics.bot_interactions.sql_executed IS 'Был ли выполнен SQL запрос';
COMMENT ON COLUMN analytics.bot_interactions.sql_execution_time_ms IS 'Время выполнения запроса в миллисекундах';
COMMENT ON COLUMN analytics.bot_interactions.table_generated IS 'Была ли сгенерирована Excel таблица';

-- Индексы для улучшения производительности
CREATE INDEX IF NOT EXISTS idx_bot_interactions_user ON analytics.bot_interactions(slack_user_id);
CREATE INDEX IF NOT EXISTS idx_bot_interactions_session ON analytics.bot_interactions(session_id);
CREATE INDEX IF NOT EXISTS idx_bot_interactions_created ON analytics.bot_interactions(created_at);
CREATE INDEX IF NOT EXISTS idx_bot_interactions_query_type ON analytics.bot_interactions(query_type);

-- Полезные запросы для аналитики:

-- Топ активных пользователей
-- SELECT
--     bu.real_name,
--     bu.slack_username,
--     COUNT(*) as total_requests,
--     SUM(CASE WHEN bi.table_generated THEN 1 ELSE 0 END) as tables_generated,
--     MAX(bi.created_at) as last_request
-- FROM analytics.bot_interactions bi
-- JOIN analytics.bot_users bu ON bi.slack_user_id = bu.slack_user_id
-- GROUP BY bu.real_name, bu.slack_username
-- ORDER BY total_requests DESC
-- LIMIT 10;

-- Самые популярные запросы
-- SELECT
--     bi.user_message,
--     COUNT(*) as count,
--     STRING_AGG(DISTINCT bu.real_name, ', ') as users
-- FROM analytics.bot_interactions bi
-- JOIN analytics.bot_users bu ON bi.slack_user_id = bu.slack_user_id
-- WHERE bi.query_type = 'data_extraction'
-- GROUP BY bi.user_message
-- ORDER BY count DESC
-- LIMIT 20;

-- Конверсия в таблицы
-- SELECT
--     COUNT(*) as total_queries,
--     SUM(CASE WHEN table_generated THEN 1 ELSE 0 END) as tables_generated,
--     ROUND(100.0 * SUM(CASE WHEN table_generated THEN 1 ELSE 0 END) / COUNT(*), 2) as conversion_rate
-- FROM analytics.bot_interactions
-- WHERE query_type = 'data_extraction';

-- Самые медленные запросы
-- SELECT
--     user_message,
--     sql_query,
--     sql_execution_time_ms,
--     rows_returned,
--     created_at
-- FROM analytics.bot_interactions
-- WHERE sql_executed = TRUE
-- ORDER BY sql_execution_time_ms DESC
-- LIMIT 10;
