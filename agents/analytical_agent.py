"""
Analytical Agent
Analyzes data extraction queries using schema documentation from YML files
Executes SQL and provides real data insights
"""
import re
from typing import Dict, Any, Optional, Tuple
from anthropic import Anthropic
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger(__name__, "INFO")


class AnalyticalAgent:
    """Analyzes queries and provides insights with real data before Excel export."""

    def __init__(
        self,
        api_key: str,
        schema_docs: Dict[str, Any],
        sql_generator,
        db_manager,
        model: str = "claude-sonnet-4-5-20250929"
    ):
        """
        Initialize analytical agent.

        Args:
            api_key: Anthropic API key
            schema_docs: Schema documentation loaded from YML files
            sql_generator: SQLGenerator instance for query generation
            db_manager: DatabaseManager instance for query execution
            model: Model to use for analysis
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.schema_docs = schema_docs
        self.sql_generator = sql_generator
        self.db_manager = db_manager

        # Build context from schema documentation
        self.schema_context = self._build_schema_context()

        self.analysis_prompt = """Ты аналитик данных Hero's Journey. Тебе предоставлены РЕАЛЬНЫЕ данные из базы.

Твоя задача - проанализировать данные и дать длинный, при этом очень информативный анализ.

**Формат ответа:**

1. Начни с основного вывода (например: "Нашел X пользователей...")
2. Дай 5-10 ключевых инсайтов (bullets)
3. Если есть временные данные - покажи распределение
4. Если данных много, упомяни что пользователь может попросить выгрузку в Excel (скажи "выгрузи в Excel" если нужен файл)

**Стиль:**
- Конкретные цифры, не общие фразы
- Дружелюбный тон
- Используй эмодзи умеренно
- На русском языке
- Краткость и ценность

**Пример хорошего ответа:**

Нашел 61 пользователя, у которых заканчивается HeroPass на этой неделе (с 10 по 17 ноября):

Основные выводы:
• Большинство подписок истекают 10-16 ноября
• Преобладают Годовые Hero's Pass (годовые абонементы)
• Первые истечения уже сегодня в 19:00 (10 ноября)

Распределение по датам окончания:
• 10 ноября - 12 пользователей
• 11 ноября - 8 пользователей
• 12 ноября - 5 пользователей

Если нужна выгрузка — скажи "выгрузи в Excel" 📊"""

    def _build_schema_context(self) -> str:
        """Build schema context from YML documentation."""
        context_parts = []

        # Add tables information
        if "tables" in self.schema_docs:
            context_parts.append("**Доступные таблицы:**\n")
            tables_dict = self.schema_docs["tables"]

            # Iterate through tables dictionary
            for table_name, table_info in tables_dict.items():
                description = table_info.get("description", "")
                context_parts.append(f"- `{table_name}`: {description}")

                # Add key columns
                columns = table_info.get("columns", [])
                if columns:
                    key_columns = [f"`{col['name']}` ({col.get('description', '')})"
                                   for col in columns[:5]]  # First 5 columns
                    context_parts.append(f"  Ключевые поля: {', '.join(key_columns)}")

                context_parts.append("")

        # Add business terms from glossary
        if "glossary" in self.schema_docs:
            context_parts.append("\n**Бизнес-термины (глоссарий):**\n")
            glossary = self.schema_docs["glossary"]
            for term, definition in list(glossary.items())[:10]:  # First 10 terms
                context_parts.append(f"- **{term}**: {definition}")

        return "\n".join(context_parts)

    def analyze(self, user_query: str, conversation_context: dict = None) -> Tuple[str, Optional[pd.DataFrame], Optional[str]]:
        """
        Analyze user's data extraction query by executing SQL and analyzing results.
        Retries up to 2 times if SQL execution fails, passing the error back to Claude.

        Args:
            user_query: User's data extraction request
            conversation_context: Optional dict with previous conversation context for follow-up queries

        Returns:
            Tuple of (analysis_text, dataframe, sql_query)
            - analysis_text: Analysis with insights and question
            - dataframe: Query results (for Excel generation later)
            - sql_query: Generated SQL query
        """
        max_retries = 10
        last_error = None
        last_sql = None
        tried_tables = set()  # Track schema.table already tried to avoid repeat loops

        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Analyzing query with real data (attempt {attempt + 1}): {user_query[:100]}")

                # Step 1: Generate SQL query (pass error from previous attempt for self-correction)
                logger.info("Generating SQL query...")
                if attempt == 0:
                    sql_query = self.sql_generator.generate_query(user_query, conversation_context)
                else:
                    logger.info(f"Retrying SQL generation with error feedback: {last_error}")
                    sql_query = self.sql_generator.generate_query_with_error(
                        user_query, last_sql, str(last_error), conversation_context,
                        tried_tables=tried_tables
                    )
                last_sql = sql_query
                logger.info(f"Generated SQL: {sql_query[:100]}...")

                # Track which schema.table was used in this attempt
                for m in re.finditer(r'FROM\s+([\w]+)\.([\w]+)', sql_query, re.IGNORECASE):
                    tried_tables.add(f"{m.group(1)}.{m.group(2)}")
                if tried_tables:
                    logger.info("Tried tables so far: %s", ", ".join(sorted(tried_tables)))

                # Step 2: Execute query
                logger.info("Executing SQL query...")
                df = self.db_manager.execute_query(sql_query)

                # Step 3: Check if we have data — treat empty result as failure and retry
                if df is None or df.empty:
                    logger.warning("Query returned no data, will retry with different approach")
                    last_error = "Запрос вернул 0 строк. Данных в этой таблице нет — нужна другая таблица или схема."
                    if attempt < max_retries:
                        continue
                    # All retries exhausted — return empty result message
                    return (
                        "Запрос выполнен успешно, но не вернул данных даже после нескольких попыток. Возможно, таких данных нет в базе. 🤔",
                        None,
                        sql_query
                    )

                logger.info(f"Query returned {len(df)} rows × {len(df.columns)} columns")

                # Step 3.5: Enrich DataFrame — resolve bare IDs into human-readable names
                df = self._enrich_id_columns(df)

                # Step 4: Prepare data summary for analysis
                data_summary = self._create_data_summary(df)

                # Step 5: Analyze with Claude
                logger.info("Analyzing data with AI...")
                response = self.client.messages.create(
                    model=self.model,
                    system=self.analysis_prompt,
                    messages=[
                        {"role": "user", "content": f"""Запрос пользователя: {user_query}

Данные из базы:
{data_summary}

Проанализируй эти данные и дай инсайты."""}
                    ],
                    temperature=0.7,
                    max_tokens=1000
                )

                analysis = response.content[0].text.strip()
                logger.info("Analysis with real data generated successfully")

                # Save successful pattern to bot_query_patterns for future reuse
                try:
                    self.db_manager.save_query_pattern(
                        question=user_query,
                        sql_query=sql_query,
                        row_count=len(df)
                    )
                except Exception as save_err:
                    logger.warning("Could not save query pattern: %s", save_err)

                return (analysis, df, sql_query)

            except Exception as e:
                last_error = e
                logger.error(f"Error during analysis (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    logger.info(f"Will retry with error feedback...")
                    continue

        return (
            f"""Произошла ошибка при анализе данных: {str(last_error)} 😔

Попробуйте переформулировать запрос или уточнить критерии.""",
            None,
            last_sql
        )

    # Maps a FK column name to (schema, table, name_column)
    # These are the most common FK columns that carry bare IDs users never want to see
    _FK_LOOKUPS = {
        "award":        ("raw",         "award",         "name"),
        "marathonevent":("raw",         "marathonevent", "name"),
        "event":        ("raw",         "event",         "name"),
        "clan":         ("raw",         "clan",          "name"),
        "user":         ("raw",         "user",          "username"),
        "booking":      ("raw",         "booking",       "id"),   # no good name col, skip
    }
    # MongoDB-style ObjectId: exactly 24 hex chars
    _OBJECTID_RE = re.compile(r'^[0-9a-f]{24}$', re.IGNORECASE)

    def _enrich_id_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Post-process DataFrame: for columns that contain bare IDs (FK references),
        lookup the human-readable name and add a new '*_name' column next to the ID column.
        Modifies df in place and returns it.
        """
        if df is None or df.empty:
            return df

        for col in list(df.columns):
            # Skip if already has a sibling _name column
            if f"{col}_name" in df.columns:
                continue

            col_lower = col.lower()

            # Check if column is a known FK
            lookup = self._FK_LOOKUPS.get(col_lower)

            # Also auto-detect: column name ends in 'id' or the values look like MongoDB ObjectIds
            if lookup is None:
                sample_vals = df[col].dropna().astype(str).head(5).tolist()
                all_objectids = sample_vals and all(self._OBJECTID_RE.match(v) for v in sample_vals)
                if not all_objectids:
                    continue
                # Try to guess table from column name (e.g. "awardid" → "award")
                guessed_table = col_lower.rstrip("id").rstrip("_")
                lookup = ("raw", guessed_table, "name")

            schema, table, name_col = lookup
            # Skip degenerate lookups (e.g. booking has no useful name)
            if name_col == "id":
                continue

            # Collect unique IDs to look up
            unique_ids = df[col].dropna().astype(str).unique().tolist()
            if not unique_ids:
                continue

            try:
                placeholders = ",".join(["%s"] * len(unique_ids))
                sql = f'SELECT id, "{name_col}" FROM "{schema}"."{table}" WHERE id IN ({placeholders})'
                with self.db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(sql, unique_ids)
                        rows = cur.fetchall()

                if not rows:
                    continue

                id_to_name = {row[0]: row[1] for row in rows}
                new_col = f"{col}_name"
                df.insert(
                    df.columns.get_loc(col) + 1,
                    new_col,
                    df[col].astype(str).map(id_to_name)
                )
                resolved = sum(1 for v in df[new_col] if v and str(v) != "nan")
                logger.info("Enriched column '%s' → '%s': %d/%d IDs resolved from %s.%s",
                            col, new_col, resolved, len(df), schema, table)

            except Exception as e:
                logger.warning("Could not enrich column '%s' from %s.%s: %s", col, schema, table, e)

        return df

    def _create_data_summary(self, df: pd.DataFrame) -> str:
        """Create a concise summary of DataFrame for AI analysis."""
        summary_parts = []

        # Basic stats
        summary_parts.append(f"Всего записей: {len(df)}")
        summary_parts.append(f"Колонки: {', '.join(df.columns.tolist())}")

        # Show first few rows
        summary_parts.append("\nПервые записи:")
        summary_parts.append(df.head(10).to_string(index=False))

        # Value counts for categorical columns (if reasonable size)
        for col in df.columns:
            if df[col].dtype == 'object' and df[col].nunique() < 20:
                value_counts = df[col].value_counts()
                summary_parts.append(f"\nРаспределение по '{col}':")
                summary_parts.append(value_counts.head(10).to_string())

        # Date columns distribution
        date_cols = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower() or '_at' in col.lower()]
        for col in date_cols:
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                if not df[col].isna().all():
                    summary_parts.append(f"\nРаспределение по '{col}':")
                    date_counts = df[col].dt.date.value_counts().sort_index()
                    summary_parts.append(date_counts.head(15).to_string())
            except:
                pass

        return "\n".join(summary_parts)
