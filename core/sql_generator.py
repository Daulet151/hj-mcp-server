"""
SQL query generation using OpenAI and schema documentation.
"""
import re
from typing import Dict, Any
from openai import OpenAI
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SQLGenerator:
    """Generates SQL queries from natural language using OpenAI."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        Initialize SQL generator.

        Args:
            api_key: OpenAI API key
            model: OpenAI model to use
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.system_prompt = ""

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
            messages = [
                {"role": "system", "content": self.system_prompt},
            ]

            if conversation_context:
                context_msg = self._build_context_message(conversation_context)
                messages.append({"role": "system", "content": context_msg})
                logger.info("Added conversation context to SQL generation")

            messages.append({"role": "user", "content": user_prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0
            )

            sql_output = response.choices[0].message.content.strip()

            # Extract SQL from markdown code blocks if present
            sql_output = self._extract_sql_from_response(sql_output)

            logger.info("Generated SQL query successfully")
            logger.debug("SQL: %s", sql_output)

            return sql_output

        except Exception as e:
            logger.error("Failed to generate SQL: %s", str(e))
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
