"""
Query Refinement Agent
Modifies existing SQL queries based on user follow-up requests
"""
from typing import Tuple, Optional
from openai import OpenAI
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger(__name__, "INFO")


class QueryRefinementAgent:
    """
    Handles query refinement - modifying existing SQL based on follow-up requests.

    Example:
    Original query: "Сколько атлетов вступило в кланы в сентябре?"
    SQL: SELECT COUNT(*) FROM userclantransaction WHERE month = 'September'

    Follow-up: "А из них сколько имеют ХП?"
    Refined SQL: SELECT COUNT(*) FROM userclantransaction t
                 JOIN subscriptions s ON t.user = s.user
                 WHERE month = 'September' AND s.has_heropass = true
    """

    def __init__(self, api_key: str, schema_docs: dict, model: str = "gpt-4o"):
        """
        Initialize query refinement agent.

        Args:
            api_key: OpenAI API key
            schema_docs: Schema documentation
            model: Model to use
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.schema_docs = schema_docs

        self.system_prompt = """Ты SQL эксперт для Hero's Journey, специализирующийся на рефакторинге запросов.

**Твоя задача:**
Пользователь уже получил данные по SQL запросу. Теперь он хочет УТОЧНИТЬ/ДОПОЛНИТЬ этот запрос.
Ты должен МОДИФИЦИРОВАТЬ существующий SQL, чтобы ответить на новый вопрос.

**Важные правила:**

1. **НЕ пиши SQL с нуля!** Бери существующий SQL и модифицируй его.

2. **Сохраняй логику оригинального запроса:**
   - Если был COUNT(*) - оставь COUNT(*)
   - Если была группировка - сохрани её
   - Если были фильтры - добавь новые, не удаляй старые

3. **Типичные уточнения:**
   - "из них сколько имеют ХП?" → добавь JOIN с подписками + фильтр
   - "только мужчины" → добавь WHERE sex = 'male'
   - "старше 25 лет" → добавь WHERE age > 25
   - "с активной подпиской" → добавь JOIN и фильтр

4. **Используй schema docs** для правильных JOIN'ов:
   - Проверяй названия таблиц и колонок
   - Используй правильные FK связи
   - Применяй business_rules из документации

5. **Формат ответа:**
```json
{
  "refined_sql": "MODIFIED SQL HERE",
  "explanation": "Что изменилось в SQL (1-2 предложения на русском)"
}
```

**Примеры:**

Original SQL:
```sql
SELECT COUNT(*) as count,
       EXTRACT(MONTH FROM created_at) as month
FROM userclantransaction
WHERE created_at >= '2025-09-01' AND created_at < '2025-12-01'
GROUP BY month
```

User refinement: "из них сколько имеют ХП?"

Refined SQL:
```sql
SELECT COUNT(DISTINCT uct.user) as count,
       EXTRACT(MONTH FROM uct.created_at) as month
FROM userclantransaction uct
JOIN userheropass uhp ON uct.user = uhp.user
WHERE uct.created_at >= '2025-09-01'
  AND uct.created_at < '2025-12-01'
  AND uhp.status = 'active'
  AND (uhp.is_dropped IS NULL OR uhp.is_dropped = false)
GROUP BY month
```

Explanation: "Добавил JOIN с таблицей userheropass и фильтр на активную подписку."

---

Original SQL:
```sql
SELECT id, firstname, lastname, points
FROM raw.user
WHERE points > 1000
ORDER BY points DESC
LIMIT 10
```

User refinement: "только женщины"

Refined SQL:
```sql
SELECT id, firstname, lastname, points, sex
FROM raw.user
WHERE points > 1000
  AND sex = 'female'
ORDER BY points DESC
LIMIT 10
```

Explanation: "Добавил фильтр по полу (sex = 'female')."

**Стиль:**
- Используй PostgreSQL синтаксис
- Форматируй SQL читабельно
- Всегда проверяй NULL значения (is_dropped, isdeleted)
- Используй алиасы для таблиц при JOIN'ах"""

    def refine_query(
        self,
        original_sql: str,
        original_user_query: str,
        refinement_request: str,
        sql_generator,
        db_manager
    ) -> Tuple[str, pd.DataFrame, str]:
        """
        Refine existing SQL query based on user's follow-up request.

        Args:
            original_sql: Original SQL query
            original_user_query: Original user question
            refinement_request: User's refinement ("из них сколько имеют ХП?")
            sql_generator: SQLGenerator instance (for schema context)
            db_manager: DatabaseManager instance (to execute refined SQL)

        Returns:
            Tuple of (analysis, dataframe, refined_sql)
        """
        try:
            logger.info(f"Refining query: '{refinement_request[:100]}'")
            logger.info(f"Original SQL: {original_sql[:200]}...")

            # Build schema context
            schema_context = self._build_schema_context()

            # Create prompt for SQL refinement
            prompt = f"""**Исходный запрос пользователя:**
{original_user_query}

**Текущий SQL:**
```sql
{original_sql}
```

**Уточнение от пользователя:**
{refinement_request}

**Доступные таблицы и связи:**
{schema_context}

Модифицируй SQL чтобы ответить на уточняющий вопрос. Отвечай в JSON формате."""

            # Call GPT to refine SQL
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )

            # Parse response
            import json
            result = json.loads(response.choices[0].message.content)
            refined_sql = result.get("refined_sql", "")
            explanation = result.get("explanation", "")

            logger.info(f"SQL refined. Explanation: {explanation}")
            logger.info(f"Refined SQL: {refined_sql[:200]}...")

            if not refined_sql:
                raise ValueError("Failed to generate refined SQL")

            # Execute refined SQL
            dataframe = db_manager.execute_query(refined_sql)
            logger.info(f"Refined query returned {len(dataframe)} rows")

            # Generate analysis of refined results
            analysis = self._generate_analysis(
                dataframe=dataframe,
                refined_sql=refined_sql,
                original_query=original_user_query,
                refinement=refinement_request,
                explanation=explanation
            )

            return analysis, dataframe, refined_sql

        except Exception as e:
            logger.error(f"Error in query refinement: {e}")
            raise

    def _build_schema_context(self) -> str:
        """Build schema context from docs."""
        context_parts = []

        if "tables" in self.schema_docs:
            tables_dict = self.schema_docs["tables"]

            # List key tables
            key_tables = ["raw.user", "userheropass", "userclantransaction", "subscription"]

            for table_name in key_tables:
                if table_name in tables_dict or table_name.split('.')[-1] in tables_dict:
                    # Handle both full and short table names
                    table_key = table_name if table_name in tables_dict else table_name.split('.')[-1]
                    table_info = tables_dict.get(table_key, {})

                    description = table_info.get("description", "")
                    context_parts.append(f"- {table_name}: {description}")

                    # Add FK relationships
                    columns = table_info.get("columns", [])
                    fk_cols = [col for col in columns if col.get("role") == "FK"]
                    if fk_cols:
                        fk_info = ", ".join([f"{col['name']} -> {col.get('business_notes', '')}"
                                            for col in fk_cols[:3]])
                        context_parts.append(f"  Связи: {fk_info}")

        return "\n".join(context_parts) if context_parts else "No schema info available"

    def _generate_analysis(
        self,
        dataframe: pd.DataFrame,
        refined_sql: str,
        original_query: str,
        refinement: str,
        explanation: str
    ) -> str:
        """
        Generate natural language analysis of refined query results.

        Args:
            dataframe: Results from refined query
            refined_sql: The refined SQL
            original_query: Original user question
            refinement: User's refinement request
            explanation: What changed in SQL

        Returns:
            Analysis text
        """
        try:
            # Prepare data summary
            data_summary = self._summarize_dataframe(dataframe)

            prompt = f"""Проанализируй результаты УТОЧНЁННОГО запроса.

**Исходный запрос:** {original_query}
**Уточнение:** {refinement}
**Что изменилось в SQL:** {explanation}

**Результаты уточнённого запроса:**
{data_summary}

Дай короткий анализ (3-5 предложений):
1. Ответ на уточняющий вопрос
2. Ключевая статистика
3. Если есть разбивка - покажи распределение

**Стиль:**
- Конкретные цифры
- Дружелюбный тон
- На русском
- В конце спроси: "Желаете чтобы я сгенерировал для вас таблицу с этими данными? 📊"

НЕ повторяй весь предыдущий анализ, отвечай только на УТОЧНЕНИЕ!"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты AI аналитик данных Hero's Journey."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error generating analysis: {e}")
            # Fallback to simple response
            return f"Результаты уточнённого запроса: {len(dataframe)} записей. Желаете сгенерировать таблицу? 📊"

    def _summarize_dataframe(self, df: pd.DataFrame) -> str:
        """Create a text summary of DataFrame for analysis."""
        if df.empty:
            return "Нет данных"

        summary_parts = [
            f"Количество записей: {len(df)}",
            f"Колонки: {', '.join(df.columns.tolist())}"
        ]

        # Show first few rows
        preview = df.head(10).to_string(index=False, max_colwidth=50)
        summary_parts.append(f"\nПервые записи:\n{preview}")

        # Add basic statistics for numeric columns
        numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
        if len(numeric_cols) > 0:
            stats = df[numeric_cols].describe().to_string()
            summary_parts.append(f"\nСтатистика:\n{stats}")

        return "\n\n".join(summary_parts)
