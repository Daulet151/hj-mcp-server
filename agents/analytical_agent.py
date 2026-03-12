"""
Analytical Agent — multi-step agentic loop.
Uses Claude tool-use to let the model autonomously run multiple SQL queries,
inspect schemas, and build a comprehensive analysis before responding.
"""
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from anthropic import Anthropic
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger(__name__, "INFO")

# Maximum agentic loop iterations to prevent runaway
MAX_ITERATIONS = 8
# Maximum length of final response (Slack limit ~4000 chars)
MAX_RESPONSE_LENGTH = 3800
# Max consecutive DB errors before stopping
MAX_DB_ERRORS = 2


class AnalyticalAgent:
    """Analyzes queries via an agentic tool-use loop with real data."""

    # ── Tool definitions for Claude ──────────────────────────────────────
    TOOLS = [
        {
            "name": "run_sql",
            "description": (
                "Execute a SELECT SQL query against the PostgreSQL database and return results. "
                "Use this to fetch data for analysis. Only SELECT queries are allowed. "
                "Returns a JSON object with 'columns' (list of column names), "
                "'rows' (list of row dicts, max 50 shown), 'total_rows' (actual count), "
                "and 'preview' (first 50 rows as text). "
                "If the query fails, returns an 'error' field with the error message."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A valid PostgreSQL SELECT query"
                    }
                },
                "required": ["sql"]
            }
        },
        {
            "name": "list_tables",
            "description": (
                "List all available tables in the database grouped by schema. "
                "Schemas: ods_core, ris, raw, stage, olap_schema. "
                "Returns a dict: schema_name -> list of table names."
            ),
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "get_table_columns",
            "description": (
                "Get column names and types for a specific table. "
                "Returns a list of column info objects with 'column_name' and 'data_type'."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "schema": {
                        "type": "string",
                        "description": "Schema name (e.g. 'raw', 'ods_core', 'olap_schema')"
                    },
                    "table": {
                        "type": "string",
                        "description": "Table name"
                    }
                },
                "required": ["schema", "table"]
            }
        },
    ]

    def __init__(
        self,
        api_key: str,
        schema_docs: Dict[str, Any],
        sql_generator,
        db_manager,
        model: str = "claude-sonnet-4-5-20250929"
    ):
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.schema_docs = schema_docs
        self.sql_generator = sql_generator
        self.db_manager = db_manager

        self.schema_context = self._build_schema_context()

    # ── Public entry point (same signature as before) ────────────────────
    def analyze(
        self, user_query: str, conversation_context: dict = None
    ) -> Tuple[str, Optional[pd.DataFrame], Optional[str]]:
        """
        Analyze user's data query using an agentic tool-use loop.

        Returns:
            Tuple of (analysis_text, dataframe_of_last_query, last_sql)
        """
        logger.info("Starting agentic analysis for: %s", user_query[:120])

        system_prompt = self._build_system_prompt(conversation_context)
        messages: List[dict] = [{"role": "user", "content": user_query}]

        last_df: Optional[pd.DataFrame] = None
        last_sql: Optional[str] = None
        all_sqls: list = []
        consecutive_db_errors = 0

        for iteration in range(MAX_ITERATIONS):
            logger.info("Agent loop iteration %d", iteration + 1)

            response = self.client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=messages,
                tools=self.TOOLS,
                temperature=0.3,
                max_tokens=4096,
            )

            # If model returns end_turn or no tool use → it's the final answer
            if response.stop_reason == "end_turn":
                analysis = self._extract_text(response)
                # Truncate if too long for Slack
                if len(analysis) > MAX_RESPONSE_LENGTH:
                    analysis = analysis[:MAX_RESPONSE_LENGTH] + "\n\n_(ответ сокращён, попросите выгрузку в Excel для полных данных)_"
                logger.info("Agent finished after %d iterations", iteration + 1)

                # Enrich the last dataframe if we have one
                if last_df is not None and not last_df.empty:
                    last_df = self._enrich_id_columns(last_df)

                # Save successful pattern
                if last_sql and last_df is not None and not last_df.empty:
                    try:
                        self.db_manager.save_query_pattern(
                            question=user_query,
                            sql_query=last_sql,
                            row_count=len(last_df)
                        )
                    except Exception as e:
                        logger.warning("Could not save query pattern: %s", e)

                return (analysis, last_df, last_sql)

            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                logger.info("Agent calls tool: %s", tool_name)

                result = self._execute_tool(tool_name, tool_input)

                # Track consecutive DB connection errors
                if "error" in result and "timeout" in str(result["error"]).lower():
                    consecutive_db_errors += 1
                    if consecutive_db_errors >= MAX_DB_ERRORS:
                        logger.warning("Too many DB timeouts (%d), forcing early stop", consecutive_db_errors)
                        result["error"] += " STOP: Database connection unstable. Use data you already have to answer."
                else:
                    consecutive_db_errors = 0

                # Track SQL results
                if tool_name == "run_sql" and "error" not in result:
                    last_sql = tool_input.get("sql")
                    all_sqls.append(last_sql)
                    if result.get("total_rows", 0) > 0:
                        # Re-execute to get full DataFrame (tool result is truncated)
                        try:
                            last_df = self.db_manager.execute_query(last_sql)
                        except Exception:
                            pass

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result, ensure_ascii=False, default=str)
                })

            # Append assistant response + tool results to messages
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        # Exhausted iterations — ask model for final answer without tools
        logger.warning("Agent loop exhausted %d iterations, forcing final answer", MAX_ITERATIONS)
        messages.append({
            "role": "user",
            "content": "Пожалуйста, дай финальный ответ на основе уже собранных данных."
        })
        response = self.client.messages.create(
            model=self.model,
            system=system_prompt,
            messages=messages,
            max_tokens=2000,
            temperature=0.5,
        )
        analysis = self._extract_text(response)
        if len(analysis) > MAX_RESPONSE_LENGTH:
            analysis = analysis[:MAX_RESPONSE_LENGTH] + "\n\n_(ответ сокращён)_"

        if last_df is not None and not last_df.empty:
            last_df = self._enrich_id_columns(last_df)

        return (analysis, last_df, last_sql)

    # ── Tool execution ───────────────────────────────────────────────────
    def _execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        """Execute a tool call and return the result as a dict."""

        if tool_name == "run_sql":
            return self._tool_run_sql(tool_input["sql"])
        elif tool_name == "list_tables":
            return self._tool_list_tables()
        elif tool_name == "get_table_columns":
            return self._tool_get_table_columns(tool_input["schema"], tool_input["table"])
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def _tool_run_sql(self, sql: str) -> dict:
        """Execute SQL and return structured result."""
        # Safety: only SELECT allowed
        sql_stripped = sql.strip().upper()
        if not sql_stripped.startswith("SELECT") and not sql_stripped.startswith("WITH"):
            return {"error": "Only SELECT queries are allowed. No INSERT/UPDATE/DELETE/DROP."}

        logger.info("Executing SQL: %s", sql[:150])
        try:
            df = self.db_manager.execute_query(sql)

            if df is None or df.empty:
                return {
                    "columns": [],
                    "rows": [],
                    "total_rows": 0,
                    "preview": "Query returned 0 rows. Try a different table or adjust filters."
                }

            total_rows = len(df)
            preview_df = df.head(50)
            rows = preview_df.to_dict(orient="records")

            # Build text preview for Claude
            preview_text = preview_df.to_string(index=False, max_colwidth=60)

            logger.info("SQL returned %d rows, %d columns", total_rows, len(df.columns))

            return {
                "columns": df.columns.tolist(),
                "total_rows": total_rows,
                "rows": rows,
                "preview": preview_text
            }

        except Exception as e:
            error_msg = str(e)
            logger.error("SQL execution failed: %s", error_msg)
            return {"error": error_msg}

    def _tool_list_tables(self) -> dict:
        """List all tables grouped by schema."""
        tables = self.db_manager.get_all_schemas_tables()
        if not tables:
            return {"error": "Could not fetch table list from database"}

        result = {}
        for schema in ("ods_core", "ris", "raw", "stage", "olap_schema"):
            if schema in tables:
                result[schema] = tables[schema]
        return result

    def _tool_get_table_columns(self, schema: str, table: str) -> dict:
        """Get column names and types for a table."""
        sql = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (schema, table))
                    rows = cur.fetchall()

            if not rows:
                return {"error": f"Table {schema}.{table} not found or has no columns"}

            return {
                "table": f"{schema}.{table}",
                "columns": [
                    {"column_name": r[0], "data_type": r[1]} for r in rows
                ]
            }
        except Exception as e:
            return {"error": str(e)}

    # ── System prompt ────────────────────────────────────────────────────
    def _build_system_prompt(self, conversation_context: dict = None) -> str:
        """Build the system prompt for the agentic loop."""
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        current_year = now.year

        prompt = f"""Ты — аналитик данных Hero's Journey. У тебя есть инструменты для работы с базой данных.

## Твои инструменты:
- **run_sql** — выполнить SELECT запрос и получить результат
- **list_tables** — посмотреть список всех таблиц в БД
- **get_table_columns** — посмотреть колонки и типы данных конкретной таблицы

## Как работать:
1. Проанализируй вопрос пользователя
2. При необходимости посмотри структуру таблиц (list_tables, get_table_columns)
3. Напиши и выполни SQL запрос(ы) через run_sql
4. Если результат пустой или неточный — попробуй другую таблицу или уточни фильтры
5. Если нужно — сделай несколько запросов для полного анализа (разбивка по категориям, сравнение периодов и т.д.)
6. Когда собрал достаточно данных — дай финальный анализ

## Правила SQL:
- Только SELECT запросы
- Используй двойные кавычки "" для зарезервированных слов PostgreSQL: "user", "event", "group", "level", "status", "type", "comment", "name", "cost", "program"
- Одинарные кавычки '' для строковых значений
- Если колонка содержит FK (ID другой таблицы) — делай JOIN чтобы показать название, не голый ID
- Приоритет схем: ods_core > ris > raw > stage > olap_schema
- Timezone: Asia/Almaty

## Текущая дата: {current_date}, год: {current_year}
- Если пользователь НЕ указал год — используй {current_year}
- Для относительных дат ('вчера', 'неделю назад') считай от {current_date}

## Формат финального ответа:
- Начни с основного вывода с конкретными цифрами
- Дай 5-10 ключевых инсайтов (bullets)
- Если есть распределения — покажи их
- Если данных много — упомяни возможность выгрузки в Excel
- Дружелюбный тон, на русском, эмодзи умеренно

{self.schema_context}
"""
        # Add conversation context for follow-ups
        if conversation_context:
            prompt += "\n## Контекст предыдущего разговора:\n"
            if conversation_context.get("previous_question"):
                prompt += f"Предыдущий вопрос: {conversation_context['previous_question']}\n"
            if conversation_context.get("previous_sql"):
                prompt += f"Предыдущий SQL:\n{conversation_context['previous_sql']}\n"
            if conversation_context.get("history"):
                prompt += "\nПоследние сообщения:\n"
                for msg in conversation_context["history"][-3:]:
                    prompt += f"  Пользователь: {msg['user_message']}\n"
                    if msg.get("sql_query"):
                        prompt += f"  SQL: {msg['sql_query'][:300]}\n"
            prompt += (
                "\nЕсли текущий запрос — уточнение предыдущего, "
                "модифицируй предыдущий SQL. Если новый запрос — начни с нуля.\n"
            )

        # Add schema docs (tables, glossary, mappings)
        prompt += self._build_schema_docs_section()

        # Add cached successful queries as examples
        if self.db_manager:
            try:
                cached = self.db_manager.find_similar_cached_query(
                    # We don't have user_query here, but it's in messages
                    "",  # Will be populated from messages context
                    limit=3
                )
                if cached:
                    prompt += "\n## Похожие успешные запросы из истории:\n"
                    for item in cached:
                        prompt += f"Вопрос: {item['user_message']}\nSQL:\n{item['sql_query']}\n\n"
            except Exception:
                pass

        return prompt

    def _build_schema_docs_section(self) -> str:
        """Build schema documentation section for the system prompt."""
        parts = ["\n## Документация схемы БД:\n"]

        if "tables" not in self.schema_docs:
            return ""

        # Table descriptions and key columns
        parts.append("### Таблицы:\n")
        for table_name, table_data in self.schema_docs["tables"].items():
            parts.append(f"**{table_name}**: {table_data.get('description', '')}")
            columns = table_data.get("columns", [])
            if columns:
                col_strs = []
                for col in columns[:8]:
                    col_str = f"`{col['name']}` ({col['type']})"
                    if col.get('description'):
                        col_str += f" — {col['description']}"
                    col_strs.append(col_str)
                parts.append("  Колонки: " + ", ".join(col_strs))
            parts.append("")

        # Business terms
        if "glossary" in self.schema_docs:
            glossary = self.schema_docs["glossary"]

            if glossary.get("business_terms"):
                parts.append("### Бизнес-термины:\n")
                for term in glossary["business_terms"]:
                    parts.append(f"- **{term.get('canonical', '')}**: {term.get('definition', '')}")
                    if "sql_logic" in term:
                        parts.append(f"  SQL: {term['sql_logic']}")
                    if "synonyms_ru" in term:
                        parts.append(f"  Синонимы: {', '.join(term['synonyms_ru'])}")
                parts.append("")

            # Program name mappings
            if glossary.get("program_name_mappings"):
                parts.append("### Маппинг программ:\n")
                for prog in glossary["program_name_mappings"]:
                    canonical = prog.get('canonical', '')
                    synonyms = prog.get('synonyms', [])
                    parts.append(f"'{canonical}' ← {', '.join(synonyms)}")
                parts.append("")

            # Club name mappings
            club_mappings = glossary.get("club_name_mappings", {})
            if club_mappings.get("mappings"):
                parts.append("### Маппинг клубов:\n")
                for club in club_mappings["mappings"]:
                    canonical = club.get('canonical', '')
                    synonyms = club.get('synonyms', [])
                    parts.append(f"'{canonical}' ← {', '.join(synonyms)}")
                parts.append("")

        # Examples
        if "examples" in self.schema_docs:
            parts.append("### Примеры запросов:\n")
            for example in self.schema_docs["examples"][:5]:
                parts.append(f"Вопрос: {example.get('question_ru', '')}")
                if "sql" in example and "statement" in example["sql"]:
                    parts.append(f"SQL: {example['sql']['statement']}")
                parts.append("")

        return "\n".join(parts)

    # ── Helpers ──────────────────────────────────────────────────────────
    def _extract_text(self, response) -> str:
        """Extract text content from Claude response."""
        parts = []
        for block in response.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts).strip() if parts else "Не удалось сформировать ответ."

    def _build_schema_context(self) -> str:
        """Build schema context from YML documentation."""
        context_parts = []
        if "tables" in self.schema_docs:
            context_parts.append("**Доступные таблицы:**\n")
            for table_name, table_info in self.schema_docs["tables"].items():
                description = table_info.get("description", "")
                context_parts.append(f"- `{table_name}`: {description}")
                columns = table_info.get("columns", [])
                if columns:
                    key_columns = [
                        f"`{col['name']}` ({col.get('description', '')})"
                        for col in columns[:5]
                    ]
                    context_parts.append(f"  Ключевые поля: {', '.join(key_columns)}")
                context_parts.append("")

        if "glossary" in self.schema_docs:
            context_parts.append("\n**Бизнес-термины (глоссарий):**\n")
            glossary = self.schema_docs["glossary"]
            for term, definition in list(glossary.items())[:10]:
                context_parts.append(f"- **{term}**: {definition}")

        return "\n".join(context_parts)

    # ── FK enrichment (unchanged from original) ─────────────────────────
    _FK_LOOKUPS = {
        "award":         ("raw", "award",         "name"),
        "marathonevent": ("raw", "marathonevent", "name"),
        "event":         ("raw", "event",         "name"),
        "clan":          ("raw", "clan",          "name"),
        "user":          ("raw", "user",          "username"),
        "booking":       ("raw", "booking",       "id"),
    }
    _OBJECTID_RE = re.compile(r'^[0-9a-f]{24}$', re.IGNORECASE)

    def _enrich_id_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Resolve bare FK IDs into human-readable names."""
        if df is None or df.empty:
            return df

        for col in list(df.columns):
            if f"{col}_name" in df.columns:
                continue

            col_lower = col.lower()
            lookup = self._FK_LOOKUPS.get(col_lower)

            if lookup is None:
                sample_vals = df[col].dropna().astype(str).head(5).tolist()
                all_objectids = sample_vals and all(self._OBJECTID_RE.match(v) for v in sample_vals)
                if not all_objectids:
                    continue
                guessed_table = col_lower.rstrip("id").rstrip("_")
                lookup = ("raw", guessed_table, "name")

            schema, table, name_col = lookup
            if name_col == "id":
                continue

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
                logger.info(
                    "Enriched column '%s' → '%s': %d/%d IDs resolved from %s.%s",
                    col, new_col, resolved, len(df), schema, table
                )
            except Exception as e:
                logger.warning("Could not enrich column '%s' from %s.%s: %s", col, schema, table, e)

        return df
