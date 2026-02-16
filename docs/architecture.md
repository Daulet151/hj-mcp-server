# Архитектура AI-аналитика для Slack Bot

## Обзор системы

Hero's Journey SQL Assistant - это мультиагентная система для анализа данных и генерации отчетов через Slack.

## Высокоуровневая архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                           SLACK WORKSPACE                           │
│                                                                     │
│  User: "Покажи пользователей с активной подпиской"                  │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ HTTP POST (Events API)
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FLASK APP (app.py)                          │
│                                                                     │
│  • Получает события из Slack                                        │
│  • Обрабатывает mentions (@bot)                                     │
│  • Логирует взаимодействия в PostgreSQL                             │
│  • Отправляет ответы обратно в Slack                                │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AGENT ORCHESTRATOR                               │
│                   (agents/orchestrator.py)                          │
│                                                                     │
│  Управляет:                                                         │
│  • Состоянием диалога (ConversationState)                           │
│  • Маршрутизацией между агентами                                    │
│  • Подтверждением генерации таблиц                                  │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
┌───────────────────┐      ┌────────────────────┐
│   CLASSIFIER      │      │  STATE MACHINE     │
│  (classifier.py)  │      │                    │
│                   │      │ States:            │
│ Классифицирует:  │      │ • INITIAL          │
│ • informational   │      │ • WAITING_FOR_     │
│ • data_extraction │      │   CONFIRMATION     │
└────────┬──────────┘      │ • GENERATING_TABLE │
         │                 └────────────────────┘
         │
         ▼
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌──────────────┐  ┌─────────────────┐
│ INFORMATIONAL│  │   ANALYTICAL    │
│    AGENT     │  │     AGENT       │
└──────────────┘  └─────────────────┘
```

## Детальная схема мультиагентной системы

```
┌─────────────────────────────────────────────────────────────────────┐
│                     USER MESSAGE IN SLACK                           │
│              "@DataAnalyzer покажи активных пользователей"         │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: QUERY CLASSIFICATION (agents/classifier.py)                │
│                                                                     │
│  QueryClassifier (GPT-4o)                                           │
│  ├─ System Prompt: "Определи тип запроса"                          │
│  ├─ Input: user message                                            │
│  └─ Output: "informational" | "data_extraction"                    │
│                                                                     │
│  Примеры классификации:                                             │
│  • "Что ты умеешь?" → informational                                │
│  • "Выведи пользователей" → data_extraction                        │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
┌──────────────────────┐  ┌──────────────────────────────────────────┐
│ INFORMATIONAL BRANCH │  │     DATA EXTRACTION BRANCH               │
└──────────────────────┘  └──────────────────────────────────────────┘
          │                       │
          │                       ▼
          │              ┌─────────────────────────────────────────────┐
          │              │ STEP 2: ANALYTICAL AGENT                    │
          │              │        (agents/analytical_agent.py)         │
          │              │                                             │
          │              │  Phase 1: SQL Generation                    │
          │              │  ├─ Загружает schema docs (YML files)      │
          │              │  ├─ SQLGenerator (core/sql_generator.py)   │
          │              │  │   • GPT-4o генерирует SQL                │
          │              │  │   • Использует schema context            │
          │              │  │   • Применяет business rules             │
          │              │  └─ Output: SQL query                       │
          │              │                                             │
          │              │  Phase 2: Query Execution                   │
          │              │  ├─ DatabaseManager (core/database.py)     │
          │              │  │   • Выполняет SQL в PostgreSQL           │
          │              │  │   • Возвращает DataFrame                 │
          │              │  └─ Output: pandas DataFrame + SQL          │
          │              │                                             │
          │              │  Phase 3: Data Analysis                     │
          │              │  ├─ GPT-4o анализирует реальные данные     │
          │              │  ├─ Генерирует инсайты (5-10 bullets)      │
          │              │  ├─ Показывает распределение               │
          │              │  └─ Спрашивает: "Сгенерировать таблицу?"   │
          │              └─────────────────────────────────────────────┘
          │                       │
          │                       ▼
          │              ┌─────────────────────────────────────────────┐
          │              │ STEP 3: WAITING FOR CONFIRMATION            │
          │              │                                             │
          │              │  State: WAITING_FOR_CONFIRMATION            │
          │              │  Stored: {dataframe, sql_query, last_query} │
          │              └─────────────────────────────────────────────┘
          │                       │
          │                       ▼
          │              ┌─────────────────────────────────────────────┐
          │              │ STEP 4: USER CONFIRMATION CHECK             │
          │              │                                             │
          │              │  Проверка:                                  │
          │              │  • "да", "yes", "давай" → TRUE              │
          │              │  • "нет", "no", "не надо" → FALSE           │
          │              └──────────┬──────────────────────────────────┘
          │                         │
          │                    ┌────┴────┐
          │                    │         │
          │              YES   │         │   NO
          │                    ▼         ▼
          │         ┌─────────────┐  ┌──────────────┐
          │         │  GENERATE   │  │   CANCEL     │
          │         │   TABLE     │  │  "Хорошо"    │
          │         └──────┬──────┘  └──────────────┘
          │                │
          │                ▼
          │       ┌────────────────────────────────────────────────────┐
          │       │ STEP 5: EXCEL GENERATION                           │
          │       │        (core/excel_generator.py)                   │
          │       │                                                    │
          │       │  ExcelGenerator:                                   │
          │       │  ├─ Создает временный XLSX файл                   │
          │       │  ├─ Форматирует данные из DataFrame               │
          │       │  ├─ Добавляет метаданные (SQL query)              │
          │       │  └─ Output: file path                             │
          │       └────────┬───────────────────────────────────────────┘
          │                │
          │                ▼
          │       ┌────────────────────────────────────────────────────┐
          │       │ STEP 6: SLACK FILE UPLOAD                          │
          │       │                                                    │
          │       │  • Upload XLSX to Slack (files.upload)             │
          │       │  • Добавить комментарий с SQL запросом             │
          │       │  • Удалить временный файл                          │
          │       └────────────────────────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      RESPONSE TO USER                               │
│                                                                     │
│  Informational: "Я AI аналитик... Вот примеры запросов:"          │
│  Analytical: "Нашел X пользователей... [инсайты]"                 │
│  + Excel file (если подтверждено)                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Компоненты системы

### 1. Flask Application (`app.py`)
**Роль:** Entry point системы

**Функции:**
- Получает события из Slack Events API
- Проверяет mentions бота
- Извлекает информацию о пользователе (Slack API)
- Логирует взаимодействия в PostgreSQL (`analytics.bot_interactions`)
- Отправляет ответы через Slack Web API
- Загружает файлы в Slack

**Ключевые эндпоинты:**
- `POST /slack/events` - получение событий от Slack
- `GET /` - health check

### 2. Agent Orchestrator (`agents/orchestrator.py`)
**Роль:** Координатор всех агентов

**Функции:**
- Управление состоянием диалога (state machine)
- Маршрутизация запросов между агентами
- Хранение контекста разговора (DataFrame, SQL)
- Обработка подтверждений пользователя

**State Machine:**
```
INITIAL → WAITING_FOR_CONFIRMATION → GENERATING_TABLE
   ↑                                       │
   └───────────────────────────────────────┘
```

**Хранимый контекст:**
```python
{
  "state": ConversationState,
  "last_query": str,           # Original user query
  "dataframe": pd.DataFrame,   # Query results
  "sql_query": str,            # Generated SQL
  "query_type": str            # informational/data_extraction
}
```

### 3. Query Classifier (`agents/classifier.py`)
**Роль:** Классификация типа запроса

**Модель:** GPT-4o (temperature=0)

**Типы запросов:**
- `informational` - вопросы о боте, функционале
- `data_extraction` - запросы на выгрузку данных

**Примеры:**
```
"Что ты умеешь?" → informational
"Выведи пользователей" → data_extraction
"Сколько активных подписок?" → data_extraction
```

### 4. Informational Agent (`agents/informational_agent.py`)
**Роль:** Отвечает на общие вопросы

**Модель:** GPT-4o

**System Prompt содержит:**
- Описание Hero's Journey
- Возможности бота
- Примеры запросов по категориям:
  - Подписки
  - Марафоны
  - Триалы
  - Платежи
  - Посещения

**Формат ответа:**
1. Ответ на вопрос
2. 2-3 примера конкретных запросов

### 5. Analytical Agent (`agents/analytical_agent.py`)
**Роль:** Анализ данных + генерация SQL + инсайты

**Модель:** GPT-4o

**3 фазы работы:**

#### Phase 1: SQL Generation
- Использует `SQLGenerator`
- Загружает schema docs из YML
- Применяет business rules
- Output: SQL query

#### Phase 2: Query Execution
- Выполняет SQL через `DatabaseManager`
- Получает реальные данные
- Output: pandas DataFrame

#### Phase 3: Data Analysis
- Анализирует реальные данные (не mock!)
- Генерирует 5-10 ключевых инсайтов
- Показывает распределения
- Обязательно спрашивает про генерацию таблицы

**Формат ответа:**
```
Нашел X пользователей...

Основные выводы:
• Инсайт 1
• Инсайт 2
...

Распределение:
• Категория 1 - N записей
• Категория 2 - M записей

Желаете чтобы я сгенерировал для вас таблицу с этими данными? 📊
```

### 6. SQL Generator (`core/sql_generator.py`)
**Роль:** Генерация SQL запросов

**Модель:** GPT-4o

**Контекст:**
- Schema documentation из YML файлов
- Business rules для каждой таблицы
- NULL semantics
- Allowed values (ENUM)
- Synonyms (для natural language)

**Особенности:**
- Валидация SQL перед выполнением
- Поддержка сложных JOIN
- Учет timezone (Asia/Almaty)
- Исключение тестовых пользователей

### 7. Schema Loader (`core/schema_loader.py`)
**Роль:** Загрузка документации таблиц

**Источник:** `docs/tables/*.yml`

**Структура YML:**
```yaml
table: schema.table_name
description: "..."
columns:
  - name: column_name
    type: data_type
    description: "..."
    synonyms_ru: [...]
    allowed_values: [...]
    business_notes: "..."
business_rules:
  - "Rule 1"
  - "Rule 2"
```

**Загруженные таблицы:**
- `raw.user` (76 колонок) - пользователи
- `raw.useraward` (12 колонок) - награды
- `olap_schema.userclantransaction` (8 колонок) - транзакции кланов
- И другие...

### 8. Database Manager (`core/database.py`)
**Роль:** Работа с PostgreSQL

**Функции:**
- Выполнение SQL запросов
- Возврат результатов как pandas DataFrame
- Connection pooling
- Error handling

**Конфигурация:**
- Host: из `config.py`
- Database: PostgreSQL
- Schema: `raw`, `olap_schema`, `analytics`

### 9. Excel Generator (`core/excel_generator.py`)
**Роль:** Генерация Excel файлов

**Функции:**
- Создание временных XLSX файлов
- Форматирование данных из DataFrame
- Добавление метаданных (SQL query, timestamp)
- Auto-sizing колонок

**Output:** Временный файл для загрузки в Slack

### 10. Analytics Database (`analytics` schema)
**Роль:** Логирование взаимодействий

**Таблицы:**

#### `analytics.bot_users`
```sql
- id (PK)
- slack_user_id
- slack_username
- real_name
- email
- display_name
- is_admin
- is_bot
- first_seen
- last_seen
```

#### `analytics.bot_interactions`
```sql
- id (PK)
- user_id (FK → bot_users)
- channel_id
- user_message
- bot_response
- query_type (informational/data_extraction)
- sql_query
- execution_time_ms
- result_rows
- error_message
- created_at
```

**Назначение:**
- Мониторинг использования бота
- Анализ популярных запросов
- Отслеживание ошибок
- Performance metrics

## Поток данных (End-to-End)

### Пример: "Покажи активных пользователей"

```
1. Slack → Flask App
   POST /slack/events
   {
     "event": {
       "text": "@DataAnalyzer покажи активных пользователей",
       "user": "U12345",
       "channel": "C67890"
     }
   }

2. Flask App → Orchestrator
   orchestrator.process_message(
     user_message="покажи активных пользователей",
     user_id="U12345",
     channel_id="C67890"
   )

3. Orchestrator → Classifier
   classifier.classify("покажи активных пользователей")
   → "data_extraction"

4. Orchestrator → Analytical Agent
   analytical_agent.analyze("покажи активных пользователей")

   4.1. Analytical Agent → SQL Generator
        sql_generator.generate_sql(
          "покажи активных пользователей",
          schema_docs
        )
        → SQL: "SELECT * FROM raw.user WHERE ..."

   4.2. Analytical Agent → Database Manager
        db_manager.execute_query(sql)
        → DataFrame (100 rows)

   4.3. Analytical Agent → GPT-4o
        "Проанализируй эти данные: [DataFrame]"
        → "Нашел 100 пользователей... [инсайты]
           Желаете таблицу? 📊"

5. Orchestrator → State Management
   conversations[(user, channel)] = {
     "state": WAITING_FOR_CONFIRMATION,
     "dataframe": df,
     "sql_query": sql,
     "last_query": "покажи активных пользователей"
   }

6. Flask App → Slack
   POST https://slack.com/api/chat.postMessage
   {
     "channel": "C67890",
     "text": "[Аналитический ответ]"
   }

7. User → "да"

8. Orchestrator → _is_confirmation("да") → True

9. Orchestrator → Excel Generator
   excel_generator.generate(df, sql)
   → /tmp/export_12345.xlsx

10. Flask App → Slack File Upload
    POST https://slack.com/api/files.upload
    {
      "file": export_12345.xlsx,
      "initial_comment": "SQL: SELECT * FROM ..."
    }

11. Cleanup
    os.remove(/tmp/export_12345.xlsx)

12. Analytics Logging
    INSERT INTO analytics.bot_interactions
    (user_id, query_type, sql_query, result_rows, ...)
```

## Конфигурация (`config.py`)

```python
class Config:
    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = "gpt-4o"

    # Slack
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

    # Database (PostgreSQL)
    DB_HOST = os.getenv("DB_HOST")
    DB_NAME = os.getenv("DB_NAME")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_PORT = int(os.getenv("DB_PORT", 5432))

    # Application
    DOCS_DIR = "docs/tables"
    LOG_LEVEL = "INFO"
```

## Ключевые особенности архитектуры

### 1. Мультиагентная система
- **Классификатор** определяет тип запроса
- **Информационный агент** отвечает на вопросы о боте
- **Аналитический агент** работает с реальными данными

### 2. State Management
- Сохранение контекста между сообщениями
- Подтверждение перед генерацией таблиц
- Очистка состояния после завершения

### 3. Schema-Driven SQL Generation
- YML файлы с полной документацией таблиц
- Business rules для каждой таблицы
- Natural language synonyms для колонок
- Автоматическая валидация значений

### 4. Real Data Analysis
- Выполнение SQL в реальной БД
- Анализ настоящих данных (не mock)
- Генерация инсайтов на основе фактов

### 5. Analytics & Monitoring
- Логирование всех взаимодействий
- Отслеживание SQL запросов
- Метрики производительности
- Error tracking

### 6. User Experience
- Дружелюбные ответы на русском
- Конкретные инсайты с цифрами
- Подтверждение перед генерацией файлов
- Excel таблицы с метаданными

## Расширяемость

### Добавление новой таблицы
1. Создать YML файл в `docs/tables/`
2. Описать колонки, синонимы, business rules
3. Перезапустить бот (автоматическая загрузка)

### Добавление нового агента
1. Создать класс в `agents/`
2. Зарегистрировать в `Orchestrator`
3. Обновить классификатор (если нужен новый тип)

### Добавление новой аналитики
1. Добавить колонку в `analytics.bot_interactions`
2. Обновить логирование в `app.py`

## Безопасность

### 1. Токены и секреты
- Все ключи в environment variables
- Валидация Slack requests (signing secret)
- Не хранятся в коде

### 2. SQL Injection Protection
- SQL генерируется через LLM (не user input напрямую)
- Валидация перед выполнением
- Read-only доступ к БД (рекомендуется)

### 3. PII Protection
- Пометка PII полей в schema docs
- Предупреждения в business_notes
- Контроль выгрузки чувствительных данных

### 4. Rate Limiting
- Slack автоматически контролирует rate limits
- OpenAI имеет свои лимиты
- Можно добавить кастомные лимиты

## Performance

### Типичные времена выполнения:
- Классификация: ~500ms (GPT-4o)
- SQL генерация: ~1-2s (GPT-4o)
- Выполнение запроса: 100ms - 5s (зависит от запроса)
- Анализ данных: ~2-3s (GPT-4o)
- Excel генерация: ~500ms
- **Total:** 5-10 секунд для полного цикла

### Оптимизации:
- Кэширование schema docs в памяти
- Connection pooling для PostgreSQL
- Async обработка для длительных запросов
- Батчинг для множественных запросов

## Мониторинг и логирование

### Логи приложения
```
[INFO] Multi-agent system initialized successfully
[INFO] Processing message in state: initial
[INFO] Classifying query: покажи активных пользователей
[INFO] Query classified as: data_extraction
[INFO] Generating SQL for query...
[INFO] SQL generated: SELECT * FROM raw.user...
[INFO] Executing SQL query...
[INFO] Query returned 100 rows in 345ms
```

### Analytics Dashboard (рекомендуется)
Запросы для мониторинга:

```sql
-- Популярные запросы
SELECT user_message, COUNT(*) as count
FROM analytics.bot_interactions
GROUP BY user_message
ORDER BY count DESC
LIMIT 10;

-- Распределение по типам
SELECT query_type, COUNT(*) as count
FROM analytics.bot_interactions
GROUP BY query_type;

-- Performance metrics
SELECT
  AVG(execution_time_ms) as avg_time,
  MAX(execution_time_ms) as max_time,
  COUNT(*) as total_queries
FROM analytics.bot_interactions
WHERE query_type = 'data_extraction';

-- Error rate
SELECT
  COUNT(CASE WHEN error_message IS NOT NULL THEN 1 END) * 100.0 / COUNT(*) as error_rate
FROM analytics.bot_interactions;
```

## Deployment

### Требования:
- Python 3.8+
- PostgreSQL 12+
- Slack Workspace с Bot User
- OpenAI API key

### Environment Variables:
```bash
OPENAI_API_KEY=sk-...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
DB_HOST=localhost
DB_NAME=herojourney
DB_USER=postgres
DB_PASSWORD=...
DB_PORT=5432
```

### Запуск:
```bash
python app.py
# Слушает на порту 3000
# Требует публичный URL для Slack Events API
```

## Будущие улучшения

### 1. Кэширование результатов
- Redis для кэша популярных запросов
- TTL по типу данных
- Invalidation при обновлении БД

### 2. Async обработка
- Celery для длительных запросов
- Progress updates в Slack
- Webhook для завершения

### 3. Расширенная аналитика
- Графики и визуализации
- Экспорт в другие форматы (CSV, PDF)
- Scheduled reports

### 4. Multi-language support
- Английский язык
- Автоопределение языка
- Перевод schema docs

### 5. Advanced SQL features
- Поддержка подзапросов
- Window functions
- CTEs (Common Table Expressions)

---

**Дата создания:** 2025-12-10
**Версия:** 1.0
**Автор:** Claude Code
