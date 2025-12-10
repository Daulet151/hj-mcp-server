# Testing Guide - Conversational AI System

## Quick Start Testing

### Test the Exact User Scenario

This is the **most critical test** - it validates the core problem that was solved.

```
Step 1: Ask initial query
User: "Сколько всего атлетов вступило в кланы в сентябре, октябре и ноябре?"

Expected Response:
- Bot generates SQL with COUNT and GROUP BY month
- Bot executes query
- Bot responds: "В сентябре: X атлетов, октябре: Y, ноябре: Z"
- Bot saves DataFrame, SQL, and analysis to context

Step 2: Ask refinement query (CRITICAL!)
User: "а из них сколько имеют ХП?"

Expected Response:
- SmartClassifier detects: query_refinement (NOT continuation, NOT new_data_query)
- QueryRefinementAgent takes original SQL
- Adds JOIN with userheropass table
- Adds WHERE filters for active status
- Re-executes refined SQL
- Bot responds: "С HeroPass: в сентябре X, октябре Y, ноябре Z"

✅ Success Criteria:
- Bot does NOT say "У меня нет данных" ❌
- Bot does NOT generate entirely new SQL from scratch ❌
- Bot DOES modify the existing SQL with JOIN ✅
- Bot DOES provide specific counts with HeroPass filter ✅

Step 3: Generate table
User: "Сгенерируй таблицу"

Expected Response:
- Bot uses refined data (with HeroPass filter)
- Generates Excel file
- Uploads to Slack
```

---

## Test Scenarios by Intent Type

### 1. Continuation (Answer from Existing Data)

**Test Case 1A: Simple name lookup**
```
User: "Покажи топ-10 пользователей по посещениям"
Bot: [returns analysis with user IDs]

User: "Как зовут первого?"
Expected: "Это Айгуль Смагулова" (reads from DataFrame)
```

**Test Case 1B: Multiple follow-ups**
```
User: "Покажи пользователей с подпиской"
Bot: [returns list]

User: "Как зовут первого?"
Bot: "Айгуль Смагулова"

User: "А сколько ей лет?"
Bot: "28 лет"

User: "Какой у нее email?"
Bot: "aigul@example.com"
```

**Success Criteria:**
- No new SQL generated ✅
- Answers come from DataFrame in memory ✅
- Natural conversational tone ✅
- Does NOT offer table generation every time ✅

---

### 2. Query Refinement (Modify SQL)

**Test Case 2A: Add filter by gender**
```
User: "Покажи топ-20 пользователей по очкам"
Bot: [returns analysis]

User: "из них только женщины"
Expected: Bot modifies SQL to add WHERE sex = 'female'
```

**Test Case 2B: Add age filter**
```
User: "Покажи пользователей"
Bot: [returns list]

User: "только старше 25 лет"
Expected: Bot adds WHERE age > 25 to existing SQL
```

**Test Case 2C: Add JOIN for subscription (CRITICAL)**
```
User: "Сколько пользователей зарегистрировалось в ноябре?"
Bot: [returns count]

User: "из них сколько с активной подпиской?"
Expected: Bot adds JOIN with subscription table + filter
```

**Success Criteria:**
- Original SQL is modified, not regenerated ✅
- New filters/JOINs added correctly ✅
- Query re-executed with refined SQL ✅
- Context updated with new DataFrame ✅

---

### 3. Table Request

**Test Case 3A: Simple confirmation**
```
User: "Покажи пользователей"
Bot: "Нашёл 150 пользователей... Сгенерировать таблицу? 📊"

User: "да"
Expected: Bot generates Excel immediately
```

**Test Case 3B: Explicit request**
```
User: "Покажи пользователей"
Bot: [returns analysis]

User: "Сгенерируй таблицу"
Expected: Bot generates Excel
```

**Test Case 3C: After refinement**
```
User: "Покажи пользователей"
Bot: [returns analysis]

User: "только женщины"
Bot: [refined analysis]

User: "сгенерируй таблицу"
Expected: Excel contains ONLY filtered data (women)
```

**Success Criteria:**
- Uses data from context ✅
- No new SQL executed ✅
- Table reflects latest refinement ✅

---

### 4. New Data Query

**Test Case 4A: Topic change**
```
User: "Покажи пользователей с подпиской"
Bot: [analysis 1]

User: "Покажи пользователей без подписки"
Expected: Bot generates NEW SQL (not refinement)
```

**Test Case 4B: Different table**
```
User: "Сколько пользователей вступило в кланы?"
Bot: [analysis about clans]

User: "Покажи всех кто получил награды"
Expected: Bot generates NEW SQL for awards (different table)
```

**Success Criteria:**
- Entirely new SQL generated ✅
- Old context data replaced ✅
- New analysis provided ✅

---

### 5. Informational

**Test Case 5A: Bot capabilities**
```
User: "Что ты умеешь?"
Expected: Bot explains its capabilities
```

**Test Case 5B: Help request**
```
User: "Помощь"
Expected: Bot provides help information
```

---

## Intent Classification Testing

### Critical Distinctions

**Continuation vs Query Refinement:**
```
"Как зовут?" → continuation (answer in data)
"из них сколько имеют ХП?" → query_refinement (needs JOIN)
```

**Query Refinement vs New Data Query:**
```
"из них только женщины" → query_refinement (modify current)
"покажи пользователей с подпиской" → new_data_query (new topic)
```

**Table Request Detection:**
```
"да" (after "Сгенерировать таблицу?") → table_request
"сгенерируй таблицу" → table_request
"выгрузи в Excel" → table_request
```

---

## Context Management Testing

### Test Case: Timeout Behavior
```
User: "Покажи пользователей"
Bot: [returns analysis with data saved]

[Wait 31 minutes]

User: "Как зовут первого?"
Expected: Bot says context expired, asks for new query
```

### Test Case: Context Persistence
```
User: "Покажи пользователей"
Bot: [analysis 1]

User: "из них только женщины"
Bot: [refined analysis 2]

User: "старше 25"
Bot: [refined again - analysis 3]

User: "Как зовут первого?"
Bot: [answers from latest refined data]

User: "Сгенерируй таблицу"
Expected: Excel contains all filters (women + age > 25)
```

---

## Logging Verification

### What to Look for in Logs:

**1. Context Creation:**
```
[INFO] Created new conversation context for ('U123', 'C456')
```

**2. Intent Classification:**
```
[INFO] Smart classifying: 'из них сколько имеют ХП?' | History: 2 msgs | Has data: True
[INFO] Intent classified as: query_refinement
```

**3. Query Refinement:**
```
[INFO] Handling query refinement (SQL modification)
[INFO] Refining query: 'из них сколько имеют ХП?'
[INFO] SQL refined. Explanation: Добавил JOIN с таблицей userheropass...
[INFO] Refined query returned 3 rows
```

**4. Continuation:**
```
[INFO] Handling continuation (follow-up question)
[INFO] Generated continuation answer (87 chars)
```

**5. Context Cleanup:**
```
[INFO] Context expired for ('U123', 'C456'), resetting
[INFO] Cleaned up 5 expired contexts
```

---

## Error Cases to Test

### Error Case 1: No Data in Memory
```
User: "Как зовут первого?"
(without any previous query)

Expected: "У меня нет данных для ответа на этот вопрос. Можете задать новый аналитический запрос?"
```

### Error Case 2: SQL Error in Refinement
```
User: "Покажи пользователей"
Bot: [analysis]

User: "из них те кто живет на Марсе"
Expected: Bot attempts refinement, but SQL might fail or return empty results
```

### Error Case 3: Expired Context
```
User: (after 30+ minutes of inactivity)
"Как зовут первого?"

Expected: Context expired message, asks for new query
```

---

## Performance Benchmarks

### Expected Response Times:

| Operation | Expected Time | What Happens |
|-----------|--------------|--------------|
| Continuation | 2-3 seconds | GPT reads DataFrame |
| Query Refinement | 4-6 seconds | GPT modifies SQL + DB execute |
| New Query | 5-10 seconds | Full SQL generation + execute |
| Table Request | 1 second | Uses cached data |
| Informational | 2-3 seconds | GPT response only |

### Memory Usage:

- **Per Context:** ~1MB (DataFrame + history)
- **100 Active Users:** ~100MB
- **Cleanup Interval:** Every 30 minutes

---

## Manual Testing Checklist

Before deploying to production, verify:

- [ ] User's exact scenario works ("из них сколько имеют ХП?")
- [ ] Continuation answers from DataFrame
- [ ] Query refinement modifies SQL correctly
- [ ] New queries generate new SQL
- [ ] Table generation uses latest data
- [ ] Context expires after 30 minutes
- [ ] Fast-path works for "да"/"нет"
- [ ] Multiple refinements chain correctly
- [ ] Conversation history persists
- [ ] Logs show correct intent classification

---

## Automated Testing

Run the test suite:

```bash
python test_conversational_system.py
```

**Tests Included:**
- ✅ ConversationContext storage and retrieval
- ✅ Message history management
- ✅ Data persistence and clearing
- ⏳ Smart classifier (requires OpenAI API)
- ⏳ Full conversation flow (requires OpenAI API)

---

## Integration Testing

### With Real Slack Bot:

1. **Start bot:** `python app.py`
2. **Open Slack workspace**
3. **Send test messages** (see scenarios above)
4. **Monitor logs** for intent classification
5. **Verify responses** match expectations
6. **Check Excel files** when generated

### With Real Database:

1. Verify SQL refinement produces valid queries
2. Check JOINs use correct foreign keys
3. Validate filters match business rules
4. Ensure NULL handling is correct

---

## Success Validation

The implementation is successful if:

✅ **Primary goal achieved:**
- "из них сколько имеют ХП?" produces correct refined counts

✅ **Natural conversation:**
- Bot remembers context for 30 minutes
- Answers follow-ups without regenerating tables
- Offers tables appropriately (not every time)

✅ **Correct routing:**
- Continuation → reads from DataFrame
- Query refinement → modifies SQL
- New query → generates new SQL
- Table request → uses cached data

✅ **No regressions:**
- All existing functionality works
- Excel generation still works
- Analytical queries still work
- Informational responses still work

---

**Ready for Testing:** ✅
**Documentation:** See [IMPLEMENTATION_COMPLETE.md](./IMPLEMENTATION_COMPLETE.md)
**Architecture:** See [CONVERSATIONAL_UPGRADE.md](./CONVERSATIONAL_UPGRADE.md)
