"""
SQL query generation using OpenAI and schema documentation.
"""
import re
from typing import Dict, Any
from anthropic import Anthropic
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SQLGenerator:
    """Generates SQL queries from natural language using OpenAI."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        """
        Initialize SQL generator.

        Args:
            api_key: Anthropic API key
            model: Anthropic model to use
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.system_prompt = ""
        self.db_manager = None  # Set after init if caching needed

    def set_schema(self, schema_docs: Dict[str, Any]):
        """
        Set schema documentation and generate system prompt.

        Args:
            schema_docs: Schema documentation loaded from YAML files
        """
        self.system_prompt = self._generate_system_prompt(schema_docs)
        logger.info("System prompt generated with %d characters", len(self.system_prompt))

    def generate_query(self, user_prompt: str, conversation_context: dict = None) -> str:
        """
        Generate SQL query from natural language prompt.

        Args:
            user_prompt: Natural language question
            conversation_context: Optional dict with previous conversation context
                - previous_sql: Last SQL query from conversation
                - previous_question: Last user question
                - history: List of recent interaction dicts

        Returns:
            Generated SQL query string

        Raises:
            Exception: If query generation fails
        """
        if not self.system_prompt:
            raise ValueError("Schema not set. Call set_schema() first.")

        logger.info("Generating SQL for prompt: %s", user_prompt[:100])

        try:
            system_text = self.system_prompt

            if conversation_context:
                context_msg = self._build_context_message(conversation_context)
                system_text += "\n\n" + context_msg
                logger.info("Added conversation context to SQL generation")

            # Inject cached successful queries as additional examples
            if self.db_manager:
                cached = self.db_manager.find_similar_cached_query(user_prompt)
                if cached:
                    cache_block = "\n=== ПОХОЖИЕ УСПЕШНЫЕ ЗАПРОСЫ ИЗ ИСТОРИИ ===\n"
                    cache_block += "Эти запросы уже успешно выполнялись — используй их как образец:\n\n"
                    for item in cached:
                        cache_block += f"Вопрос: {item['user_message']}\nSQL:\n{item['sql_query']}\n\n"
                    system_text += "\n\n" + cache_block
                    logger.info("Injected %d cached queries into prompt", len(cached))

            response = self.client.messages.create(
                model=self.model,
                system=system_text,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.0,
                max_tokens=2000
            )

            sql_output = response.content[0].text.strip()

            # Extract SQL from markdown code blocks if present
            sql_output = self._extract_sql_from_response(sql_output)

            logger.info("Generated SQL query successfully")
            logger.debug("SQL: %s", sql_output)

            return sql_output

        except Exception as e:
            logger.error("Failed to generate SQL: %s", str(e))
            raise

    def generate_query_with_error(self, user_prompt: str, failed_sql: str, error_message: str, conversation_context: dict = None) -> str:
        """
        Retry SQL generation with error feedback for self-correction.

        Args:
            user_prompt: Original natural language question
            failed_sql: The SQL that failed
            error_message: The error from the database
            conversation_context: Optional conversation context

        Returns:
            Corrected SQL query string
        """
        if not self.system_prompt:
            raise ValueError("Schema not set. Call set_schema() first.")

        logger.info("Retrying SQL generation with error feedback")

        try:
            system_text = self.system_prompt
            if conversation_context:
                context_msg = self._build_context_message(conversation_context)
                system_text += "\n\n" + context_msg

            retry_prompt = f"""Запрос пользователя: {user_prompt}

Предыдущий SQL запрос вернул ошибку:
SQL:
{failed_sql}

Ошибка PostgreSQL:
{error_message}

Исправь SQL запрос, учитывая ошибку. Используй ТОЛЬКО реальные колонки из документации схемы.
Если ошибка связана с несуществующей колонкой — удали её или замени правильной.
Верни ТОЛЬКО исправленный SQL без объяснений."""

            response = self.client.messages.create(
                model=self.model,
                system=system_text,
                messages=[{"role": "user", "content": retry_prompt}],
                temperature=0.0,
                max_tokens=2000
            )

            sql_output = response.content[0].text.strip()
            sql_output = self._extract_sql_from_response(sql_output)

            logger.info("Corrected SQL generated successfully")
            return sql_output

        except Exception as e:
            logger.error("Failed to generate corrected SQL: %s", str(e))
            raise

    def _build_context_message(self, ctx: dict) -> str:
        """
        Build conversation context message for follow-up SQL generation.

        Args:
            ctx: Dict with previous_sql, previous_question, history

        Returns:
            Context string to include in LLM messages
        """
        parts = ["КОНТЕКСТ ПРЕДЫДУЩЕГО РАЗГОВОРА:"]

        if ctx.get("previous_question"):
            parts.append(f"Предыдущий вопрос пользователя: {ctx['previous_question']}")

        if ctx.get("previous_sql"):
            parts.append(f"Предыдущий SQL запрос:\n{ctx['previous_sql']}")

        if ctx.get("history"):
            parts.append("\nПоследние сообщения:")
            for msg in ctx["history"][-3:]:
                parts.append(f"  Пользователь: {msg['user_message']}")
                if msg.get("sql_query"):
                    parts.append(f"  SQL: {msg['sql_query'][:300]}")

        parts.append(
            "\nЕсли текущий запрос является уточнением или продолжением предыдущего, "
            "модифицируй предыдущий SQL соответственно. "
            "Если это новый независимый запрос, игнорируй контекст и генерируй SQL с нуля."
        )

        return "\n".join(parts)

    def _extract_sql_from_response(self, response: str) -> str:
        """
        Extract SQL query from OpenAI response, handling markdown code blocks.

        Args:
            response: Raw response from OpenAI

        Returns:
            Clean SQL query string
        """
        # Try to extract SQL from markdown code block (```sql ... ```)
        sql_pattern = r'```sql\s*\n(.*?)\n```'
        match = re.search(sql_pattern, response, re.DOTALL | re.IGNORECASE)

        if match:
            sql = match.group(1).strip()
            logger.debug("Extracted SQL from markdown code block")
            return sql

        # Fallback: simple cleanup for responses starting with ```sql
        if response.startswith("```sql"):
            response = response[len("```sql"):].strip()
        if response.endswith("```"):
            response = response[:-len("```")].strip()

        return response

    def _generate_system_prompt(self, schema_docs: Dict[str, Any]) -> str:
        """Generate comprehensive system prompt from schema documentation."""
        prompt = """Ты — SELECT SQL-бот для базы данных Hero's Journey.

        ПРАВИЛА:
        1. Генерируй ТОЛЬКО валидный SELECT SQL без комментариев
        2. Используй ТОЛЬКО документированные таблицы и поля
        3. Учитывай timezone Asia/Almaty для всех дат
        4. Для связи таблиц используй указанные relationships
        5. Колонка "user" обязательно должна использвться с двойными кавычками "user"
        6. Запрещены: DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE

        ⚠️ ВАЖНО ПРО ГОД:
        - Если пользователь НЕ указал конкретный год в запросе, ВСЕГДА используй 2025 год
        - Примеры:
          ✅ "Покажи продажи за январь" → используй январь 2025
          ✅ "Выведи триальщиков за октябрь" → используй октябрь 2025
          ✅ "Чекины за последний месяц" → используй текущий месяц 2025 года
          ❌ НЕ спрашивай какой год, просто используй 2025
        - Если год УКАЗАН явно (например "2024", "2023") - используй указанный год

        ВАЖНО ДЛЯ НАЗВАНИЙ ПРОГРАММ:
        - Пользователи могут писать названия программ на русском или в неформальном виде
        - Ты ДОЛЖЕН конвертировать их в точные значения из allowed_values
        - Используй таблицу синонимов программ ниже для правильного маппинга
        - Римские цифры (I, II, III, IV) НЕ заменяй на арабские (1, 2, 3, 4) в SQL!

        ЧАСТЫЕ ОШИБКИ (НЕ ДЕЛАЙ):
        ❌ Использовать поля из другой таблицы без JOIN
        ❌ Выдумывать названия колонок
        ❌ Забывать про схему olap_schema
        ❌ Писать "Burn 1" вместо "Burn I"
        ❌ Писать "Берн 1" вместо "Burn I"
        ❌ Писать "Fit Body III" вместо "Fit body III"
        ✅ Правильно: используй только задокументированные поля и точные названия из allowed_values

        КРИТИЧЕСКИ ВАЖНО - ПРАВИЛА ЭКРАНИРОВАНИЯ PostgreSQL:
        ⚠️ ОБЯЗАТЕЛЬНО используй двойные кавычки "" для зарезервированных слов PostgreSQL!

        ВСЕГДА ЭКРАНИРУЙ ЭТИ ПОЛЯ:
        - "user" - ВСЕГДА в кавычках (reserved word)
        - "event" - ВСЕГДА в кавычках (reserved word)
        - "group" - ВСЕГДА в кавычках (reserved word)
        - "level" - ВСЕГДА в кавычках (reserved word)
        - "status" - ВСЕГДА в кавычках (reserved word)
        - "type" - ВСЕГДА в кавычках (reserved word)
        - "comment" - ВСЕГДА в кавычках (reserved word)
        - "name" - ВСЕГДА в кавычках (reserved word)
        - "cost" - ВСЕГДА в кавычках (reserved word)
        - "program" - ВСЕГДА в кавычках (reserved word)

        ПРАВИЛА КАВЫЧЕК:
        1. Двойные кавычки "" - для названий полей/таблиц (идентификаторов)
        ✅ SELECT "user", "event" FROM booking
        ❌ SELECT user, event FROM booking

        2. Одинарные кавычки '' - для строковых значений
        ✅ WHERE marathon_name = 'Burn I'
        ❌ WHERE marathon_name = "Burn I"

        3. Удваивай апостроф внутри строк
        ✅ WHERE marathon_name = 'Hero''s Week'
        ❌ WHERE marathon_name = 'Hero's Week'
    """

        # Add table descriptions
        prompt += "\n=== ТАБЛИЦЫ ===\n"
        for table_name, table_data in schema_docs["tables"].items():
            prompt += f"\nТаблица: {table_name}\n"
            prompt += f"Описание: {table_data.get('description', '')}\n"
            prompt += "Колонки:\n"
            for col in table_data.get("columns", []):
                prompt += f"  - {col['name']} ({col['type']}): {col.get('description', '')}\n"
                if "synonyms_ru" in col:
                    prompt += f"    Синонимы: {', '.join(col['synonyms_ru'])}\n"

        # Add business terms
        prompt += "\n=== БИЗНЕС-ТЕРМИНЫ ===\n"
        for term in schema_docs["glossary"].get("business_terms", []):
            prompt += f"\n{term.get('canonical', '')}: {term.get('definition', '')}\n"
            prompt += f"Синонимы: {', '.join(term.get('synonyms_ru', []))}\n"
            if "sql_logic" in term:
                prompt += f"SQL логика: {term['sql_logic']}\n"

        # Add program name mappings
        prompt += "\n=== МАППИНГ НАЗВАНИЙ ПРОГРАММ ===\n"
        prompt += "ВАЖНО: Пользователи могут писать названия программ по-разному.\n"
        prompt += "Конвертируй их в ТОЧНЫЕ канонические значения из этого списка:\n\n"
        for prog in schema_docs["glossary"].get("program_name_mappings", []):
            canonical = prog.get('canonical', '')
            synonyms = prog.get('synonyms', [])
            prompt += f"Каноническое: '{canonical}'\n"
            prompt += f"  Синонимы: {', '.join(synonyms)}\n"
            prompt += f"  → В SQL используй ТОЧНО: '{canonical}'\n\n"

        # Add club name mappings
        prompt += "\n=== МАППИНГ НАЗВАНИЙ КЛУБОВ ===\n"
        prompt += "ВАЖНО: Пользователи могут писать названия клубов/филиалов по-разному.\n"
        prompt += "Конвертируй их в ТОЧНЫЕ канонические значения:\n\n"
        club_mappings = schema_docs["glossary"].get("club_name_mappings", {})
        for club in club_mappings.get("mappings", []):
            canonical = club.get('canonical', '')
            synonyms = club.get('synonyms', [])
            prompt += f"Каноническое: '{canonical}'\n"
            prompt += f"  Синонимы: {', '.join(synonyms)}\n"
            prompt += f"  → В SQL используй ТОЧНО: '{canonical}'\n\n"

        # Add examples
        prompt += "\n=== ПРИМЕРЫ ЗАПРОСОВ ===\n"
        for example in schema_docs["examples"][:10]:
            prompt += f"\nВопрос: {example.get('question_ru', '')}\n"
            if "sql" in example and "statement" in example["sql"]:
                prompt += f"SQL:\n{example['sql']['statement']}\n"

        return prompt
