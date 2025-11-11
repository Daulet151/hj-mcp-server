"""
Analytical Agent
Analyzes data extraction queries using schema documentation from YML files
Executes SQL and provides real data insights
"""
from typing import Dict, Any, Optional, Tuple
from openai import OpenAI
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
        model: str = "gpt-4o"
    ):
        """
        Initialize analytical agent.

        Args:
            api_key: OpenAI API key
            schema_docs: Schema documentation loaded from YML files
            sql_generator: SQLGenerator instance for query generation
            db_manager: DatabaseManager instance for query execution
            model: Model to use for analysis
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.schema_docs = schema_docs
        self.sql_generator = sql_generator
        self.db_manager = db_manager

        # Build context from schema documentation
        self.schema_context = self._build_schema_context()

        self.analysis_prompt = """Ты аналитик данных Hero's Journey. Тебе предоставлены РЕАЛЬНЫЕ данные из базы.

Твоя задача - проанализировать данные и дать длинный, но информативный анализ.

**Формат ответа:**

1. Начни с основного вывода (например: "Нашел X пользователей...")
2. Дай 3-5 ключевых инсайтов (bullets)
3. Если есть временные данные - покажи распределение
4. ОБЯЗАТЕЛЬНО закончи вопросом: "Желаете чтобы я сгенерировал для вас таблицу с этими данными? 📊"

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

Желаете чтобы я сгенерировал для вас таблицу с этими данными? 📊"""

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

    def analyze(self, user_query: str) -> Tuple[str, Optional[pd.DataFrame], Optional[str]]:
        """
        Analyze user's data extraction query by executing SQL and analyzing results.

        Args:
            user_query: User's data extraction request

        Returns:
            Tuple of (analysis_text, dataframe, sql_query)
            - analysis_text: Analysis with insights and question
            - dataframe: Query results (for Excel generation later)
            - sql_query: Generated SQL query
        """
        try:
            logger.info(f"Analyzing query with real data: {user_query[:100]}")

            # Step 1: Generate SQL query
            logger.info("Generating SQL query...")
            sql_query = self.sql_generator.generate_query(user_query)
            logger.info(f"Generated SQL: {sql_query[:100]}...")

            # Step 2: Execute query
            logger.info("Executing SQL query...")
            df = self.db_manager.execute_query(sql_query)

            # Step 3: Check if we have data
            if df is None or df.empty:
                logger.warning("Query returned no data")
                return (
                    "Запрос выполнен успешно, но не вернул данных. Возможно, нет пользователей соответствующих критериям. 🤔",
                    None,
                    sql_query
                )

            logger.info(f"Query returned {len(df)} rows × {len(df.columns)} columns")

            # Step 4: Prepare data summary for analysis
            data_summary = self._create_data_summary(df)

            # Step 5: Analyze with OpenAI
            logger.info("Analyzing data with AI...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.analysis_prompt},
                    {"role": "user", "content": f"""Запрос пользователя: {user_query}

Данные из базы:
{data_summary}

Проанализируй эти данные и дай инсайты."""}
                ],
                temperature=0.7,
                max_tokens=1000
            )

            analysis = response.choices[0].message.content.strip()
            logger.info("Analysis with real data generated successfully")

            # Ensure the question is present
            if "сгенерировал для вас таблицу" not in analysis.lower() and \
               "сгенерирую таблицу" not in analysis.lower():
                analysis += "\n\nЖелаете чтобы я сгенерировал для вас таблицу с этими данными? 📊"

            return (analysis, df, sql_query)

        except Exception as e:
            logger.error(f"Error during analysis: {e}")
            return (
                f"""Произошла ошибка при анализе данных: {str(e)} 😔

Но я могу попробовать сгенерировать таблицу напрямую.

Желаете чтобы я сгенерировал для вас таблицу с этими данными? 📊""",
                None,
                None
            )

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
