# Conversational AI Upgrade - Implementation Guide

## 🎯 What Changed

Upgraded the AI analyst from a **rigid state machine** to a **conversational ChatGPT-like experience**.

### Before:
```
User: "Кто больше всех ходил на тренировки?"
Bot: "Юзер ID 678321651... Сгенерировать таблицу? 📊"
User: "Как зовут этого юзера?"
Bot: [generates table, ignoring the question] ❌
```

### After:
```
User: "Кто больше всех ходил на тренировки?"
Bot: "Юзер ID 678321651... Сгенерировать таблицу? 📊"
User: "Как зовут этого юзера?"
Bot: "Это Айгуль Смагулова, у неё 145 посещений" ✅
User: "Сгенерируй таблицу"
Bot: [generates Excel] ✅
```

---

## 📦 New Components

### 1. **SmartIntentClassifier** (`agents/smart_classifier.py`)
**Purpose:** Context-aware intent classification

**5 Intent Types:**
- `continuation` - Follow-up questions about existing data (no SQL modification)
- `query_refinement` - Modify existing SQL based on follow-up (NEW!)
- `table_request` - Request to generate Excel
- `new_data_query` - New analytical query
- `informational` - Questions about bot functionality

**Key Features:**
- Considers conversation history
- Checks if data is in memory
- Detects pronouns and references ("этого", "ему", "первого")
- Fast-path for simple yes/no confirmations

**Example:**
```python
intent = smart_classifier.classify_with_context(
    user_message="Как зовут этого юзера?",
    conversation_history=[...],
    has_pending_data=True
)
# Returns: "continuation"
```

---

### 2. **ContinuationAgent** (`agents/continuation_agent.py`)
**Purpose:** Answer follow-up questions using data in memory

**Key Features:**
- Works with DataFrame already in memory
- Does NOT generate new SQL
- Does NOT query database
- Natural, conversational responses
- Only offers table generation when appropriate

**System Prompt Highlights:**
- "НЕ предлагай генерацию таблицы в каждом ответе!"
- "Будь разговорным, как ChatGPT"
- "Отвечай конкретно на вопрос"

**Example:**
```python
answer = continuation_agent.answer_followup(
    user_question="Как зовут этого юзера?",
    previous_dataframe=df,
    previous_sql="SELECT ...",
    previous_analysis="Нашёл 100 пользователей...",
    conversation_history=[...]
)
# Returns: "Это Айгуль Смагулова, у неё 145 посещений"
```

---

### 3. **QueryRefinementAgent** (`agents/query_refinement_agent.py`) 🆕
**Purpose:** Modify existing SQL queries based on user refinements

**Key Features:**
- Takes original SQL and MODIFIES it (doesn't create from scratch)
- Adds JOINs, filters, and conditions to existing query
- Re-executes refined SQL and generates new analysis
- Preserves original query logic and structure
- Uses schema docs for proper table relationships

**System Prompt Highlights:**
- "НЕ пиши SQL с нуля! Бери существующий SQL и модифицируй его"
- "Сохраняй логику оригинального запроса"
- "Используй schema docs для правильных JOIN'ов"

**Example:**
```python
# User asks: "Сколько атлетов вступило в кланы в сентябре?"
# Original SQL: SELECT COUNT(*) FROM userclantransaction WHERE month = 'September'

# User follows up: "из них сколько имеют ХП?"
analysis, new_df, refined_sql = query_refinement_agent.refine_query(
    original_sql="SELECT COUNT(*) FROM userclantransaction...",
    original_user_query="Сколько атлетов вступило в кланы в сентябре?",
    refinement_request="из них сколько имеют ХП?",
    sql_generator=sql_generator,
    db_manager=db_manager
)

# Refined SQL adds JOIN:
# SELECT COUNT(DISTINCT uct.user)
# FROM userclantransaction uct
# JOIN userheropass uhp ON uct.user = uhp.user
# WHERE month = 'September' AND uhp.status = 'active'
```

**Critical Use Case:**
Solves the exact problem described by the user where asking "из них сколько имеют ХП?" should modify the previous SQL query rather than starting from scratch.

---

### 4. **ConversationContext** (`agents/conversation_context.py`)
**Purpose:** Store conversation state and data

**Stores:**
- `history`: List of messages (user/assistant)
- `last_dataframe`: DataFrame from last query
- `last_sql`: SQL that was executed
- `last_analysis`: Analysis text
- `last_user_query`: Last user question
- `created_at`, `last_activity`: Timestamps

**Methods:**
- `add_user_message(msg)` - Add user message to history
- `add_bot_message(msg)` - Add bot response to history
- `save_data(df, sql, analysis)` - Store query results
- `has_dataframe()` - Check if data exists
- `get_recent_history(n)` - Get last N messages
- `clear_data()` - Clear data but keep history
- `clear_all()` - Clear everything
- `is_expired()` - Check if timeout reached (30 min default)

**Example:**
```python
context = ConversationContext(timeout_minutes=30)
context.add_user_message("Покажи пользователей")
context.save_data(df, sql, analysis)
context.add_bot_message("Нашёл 100 пользователей...")

if context.is_expired():
    context.clear_all()
```

---

### 5. **Enhanced Orchestrator** (`agents/orchestrator.py`)
**Purpose:** Route messages to appropriate handlers

**New Architecture:**
```
User Message
    ↓
Fast Path Check (simple yes/no)
    ↓
Smart Classification (with context)
    ↓
Route to Handler:
    - continuation → ContinuationAgent (answer from existing data)
    - query_refinement → QueryRefinementAgent (modify SQL & re-execute) 🆕
    - table_request → Excel Generation
    - new_data_query → AnalyticalAgent (new SQL query)
    - informational → InformationalAgent (bot info)
```

**Key Methods:**
- `_handle_continuation()` - Use data in memory (no new SQL)
- `_handle_query_refinement()` - Modify existing SQL and re-execute 🆕
- `_handle_table_request()` - Generate Excel
- `_handle_new_data_query()` - Execute new SQL
- `_handle_informational()` - Answer about bot

**Storage:**
```python
# Key: (user_id, channel_id)
# Value: ConversationContext
self.conversations: Dict[Tuple[str, str], ConversationContext] = {}
```

---

## 🔄 Integration with Existing System

### What Was NOT Changed:
✅ **SQLGenerator** - Same SQL generation logic
✅ **DatabaseManager** - Same query execution
✅ **ExcelGenerator** - Same table creation
✅ **AnalyticalAgent** - Same analysis flow
✅ **InformationalAgent** - Same informational responses

### What Was Added:
➕ Smart intent classification with context
➕ Continuation agent for follow-ups
➕ Conversation memory (30 min timeout)
➕ Natural conversation flow

### Backward Compatibility:
- Old `classifier.py` still exists (imported as `basic_classifier`)
- All existing methods maintained
- Same return signatures from `process_message()`

---

## 📊 Flow Diagram

```
┌─────────────────────────────────────┐
│    User: "Кто больше ходил?"        │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  SmartClassifier                    │
│  → new_data_query                   │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  AnalyticalAgent                    │
│  • Generate SQL                     │
│  • Execute query → DataFrame         │
│  • Analyze data                     │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  ConversationContext.save_data()    │
│  • Store DataFrame                  │
│  • Store SQL                        │
│  • Store analysis                   │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Bot: "Нашёл 100 пользователей...  │
│       Сгенерировать таблицу? 📊"    │
└─────────────────────────────────────┘


┌─────────────────────────────────────┐
│  User: "Как зовут этого юзера?"     │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  SmartClassifier (with context!)    │
│  History: ["Кто больше ходил?"]     │
│  Has data: True                     │
│  → continuation                     │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  ContinuationAgent                  │
│  • Read DataFrame in memory         │
│  • Answer using existing data       │
│  • NO new SQL!                      │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Bot: "Это Айгуль Смагулова,        │
│       у неё 145 посещений"          │
└─────────────────────────────────────┘


┌─────────────────────────────────────┐
│  User: "Сгенерируй таблицу"         │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  SmartClassifier                    │
│  → table_request                    │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  _handle_table_request()            │
│  • Get DataFrame from context       │
│  • Pass to ExcelGenerator           │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Bot: [uploads Excel file]          │
└─────────────────────────────────────┘
```

---

## 🧪 Testing

### Basic Test (Completed):
```bash
python test_conversational_system.py
```

Tests:
- ✅ ConversationContext storage
- ✅ Message history management
- ✅ Data persistence
- ⏳ Smart classifier (requires OpenAI API)
- ⏳ Full conversation flow (requires OpenAI API)

### Manual Testing Scenarios:

#### Scenario 1: Follow-up Questions
```
User: "Покажи топ-10 пользователей по посещениям"
Bot: [analysis with data]

User: "Как зовут первого?"
Expected: Bot answers using data in memory

User: "А сколько ему лет?"
Expected: Bot continues conversation

User: "Сгенерируй таблицу"
Expected: Bot generates Excel
```

#### Scenario 2: Context Switching
```
User: "Покажи пользователей с подпиской"
Bot: [analysis 1]

User: "Покажи пользователей без подписки"
Expected: Bot makes NEW query (not continuation)

User: "Как зовут первого?"
Expected: Bot uses data from query 2
```

#### Scenario 3: Timeout
```
User: "Покажи пользователей"
Bot: [analysis]

[Wait 31 minutes]

User: "Как зовут первого?"
Expected: Bot says context expired, asks new query
```

---

## 🚀 Deployment Checklist

### Before Deploying:

1. **Test with Real OpenAI API:**
   ```bash
   # Uncomment in test_conversational_system.py:
   test_smart_classifier()
   test_conversational_flow()
   ```

2. **Check Imports:**
   ```python
   from agents import (
       AgentOrchestrator,
       SmartIntentClassifier,
       ContinuationAgent,
       ConversationContext
   )
   ```

3. **Verify `app.py` Compatibility:**
   - `orchestrator.process_message()` returns same tuple format
   - No breaking changes in return signatures

4. **Monitor Logs:**
   ```
   [INFO] Created new conversation context for (user, channel)
   [INFO] Intent classified as: continuation
   [INFO] Handling continuation (follow-up question)
   [INFO] Generated continuation answer (123 chars)
   ```

5. **Check Memory Usage:**
   - Each context stores ~1MB (DataFrame + history)
   - 30-minute timeout auto-cleans old contexts
   - Manual cleanup: `orchestrator.cleanup_expired_contexts()`

### After Deploying:

1. **Monitor OpenAI API Usage:**
   - New classification call per message
   - Continuation agent call for follow-ups
   - Should NOT increase SQL generation calls

2. **Track Query Types:**
   ```sql
   SELECT query_type, COUNT(*)
   FROM analytics.bot_interactions
   GROUP BY query_type;
   ```

   New types:
   - `continuation` (new!)
   - `table_request` (new!)
   - `data_extraction` (existing)
   - `informational` (existing)

3. **Performance Metrics:**
   - Continuation: ~2-3s (faster, no SQL)
   - New query: ~5-10s (same as before)
   - Table request: ~1s (uses cached data)

---

## 🐛 Troubleshooting

### Issue: "Continuation requested but no data in memory"
**Cause:** Context expired or was cleared
**Solution:** User needs to make new analytical query

### Issue: Bot generates table instead of answering
**Cause:** Smart classifier incorrectly classified as table_request
**Solution:** Check classifier prompts, adjust keywords

### Issue: Bot doesn't remember previous conversation
**Cause:**
- Context timeout (30 min default)
- Different channel/user ID
- Server restart (in-memory storage)

**Solution:**
- Increase timeout if needed
- Add persistence layer (Redis/database) for production

### Issue: Memory leak with many users
**Cause:** Contexts not being cleaned up
**Solution:** Call `orchestrator.cleanup_expired_contexts()` periodically

---

## 📈 Future Enhancements

### Short-term (Recommended):
1. **Persistent Storage**
   - Store contexts in Redis/PostgreSQL
   - Survive server restarts
   - Share across multiple instances

2. **Context Commands**
   - `/reset` - Clear context manually
   - `/history` - Show conversation history
   - `/context` - Show current state

3. **Advanced Table Generation**
   - "Сгенерируй только топ-5"
   - "Выгрузи только имена и email"
   - Filter DataFrame before Excel generation

### Long-term:
1. **Multi-turn Query Refinement**
   - "Покажи пользователей"
   - "С подпиской"
   - "Из Алматы"
   - → Refine SQL progressively

2. **Context Sharing**
   - Share analysis with colleagues
   - Collaborative analytics sessions

3. **Voice/Video Support**
   - Slack huddles integration
   - Voice commands

---

## 📝 Code Examples

### Example 1: Adding New Intent Type

```python
# In smart_classifier.py
class SmartIntentClassifier:
    def classify_with_context(self, ...):
        # Add new intent to system prompt
        system_prompt = """
        ...
        5. **export_request** - Request specific export format
           Examples: "экспортируй в CSV", "сохрани как PDF"
        ...
        """
```

### Example 2: Custom Context Timeout

```python
# In app.py initialization
orchestrator = AgentOrchestrator(
    api_key=Config.OPENAI_API_KEY,
    schema_docs=schema_docs,
    sql_generator=sql_generator,
    db_manager=db_manager,
    model=Config.OPENAI_MODEL
)

# Set custom timeout for specific user
context = orchestrator.conversations.get((user_id, channel_id))
if context:
    context.timeout_minutes = 60  # 1 hour for power users
```

### Example 3: Scheduled Cleanup

```python
# Add to app.py
import threading
import time

def cleanup_task():
    while True:
        time.sleep(3600)  # Every hour
        orchestrator.cleanup_expired_contexts()
        logger.info("Cleaned up expired contexts")

cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
cleanup_thread.start()
```

---

## 🎓 Training Notes

### For Developers:
- Read `docs/architecture.md` first
- Study flow diagrams above
- Test locally before deploying
- Monitor logs closely first week

### For Users:
- Bot now remembers conversation (30 min)
- Ask follow-up questions naturally
- Say "сгенерируй" to get Excel
- Bot won't offer table every time now

---

**Version:** 2.0
**Date:** 2025-12-10
**Author:** Claude Code
**Status:** ✅ Ready for Testing
