"""
Continuation Agent
Answers follow-up questions using data already in memory
"""
from typing import List, Dict, Optional
from openai import OpenAI
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger(__name__, "INFO")


class ContinuationAgent:
    """
    Handles conversational follow-up questions using data in memory.

    This agent does NOT:
    - Generate new SQL
    - Query the database
    - Fetch new data

    This agent DOES:
    - Answer questions using DataFrame in memory
    - Maintain conversational context
    - Provide natural, ChatGPT-like responses
    """

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        Initialize continuation agent.

        Args:
            api_key: OpenAI API key
            model: Model to use for responses
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model

        self.system_prompt = """Ты AI Data Analyst для Hero's Journey в режиме продолжения разговора.

**Твоя роль:**
Ты отвечаешь на уточняющие вопросы пользователя, используя данные которые УЖЕ есть в памяти из предыдущего запроса.

**У тебя есть:**
1. DataFrame с результатами предыдущего SQL запроса
2. SQL запрос который был выполнен
3. Предыдущий анализ данных
4. История разговора

**Твоя задача:**
- Ответить на вопрос пользователя естественно, как в диалоге
- Использовать данные из DataFrame
- Быть конкретным и точным
- Отвечать кратко, но информативно
- Поддерживать дружелюбный тон

**ВАЖНЫЕ ПРАВИЛА:**

1. **НЕ предлагай генерацию таблицы в каждом ответе!**
   - Упоминай про таблицу только если:
     а) Пользователь явно об этом спросил
     б) Данных слишком много для текстового ответа (>20 записей)
     в) Это первое сообщение после аналитического запроса

2. **Если данных нет в DataFrame:**
   - Честно скажи что этой информации нет в текущих данных
   - Предложи сделать новый запрос если нужно
   - Не придумывай данные!

3. **Будь разговорным:**
   - "Это Айгуль Смагулова" вместо "В столбце имя значение Айгуль Смагулова"
   - "У неё 145 посещений" вместо "Количество посещений равно 145"
   - "Ей 28 лет" вместо "Значение age составляет 28"

4. **Используй контекст:**
   - "Этот пользователь" = из предыдущего разговора
   - "Первый/последний" = из топа
   - "Он/она" = про конкретного человека

**Формат ответа:**
Просто ответь на вопрос естественным языком. БЕЗ bullet points, БЕЗ структуры, БЕЗ "Основные выводы:".
Как в обычном разговоре.

**Примеры хороших ответов:**

Вопрос: "Как зовут этого юзера?"
Ответ: "Это Айгуль Смагулова (username: aigul_sm). У неё 145 посещений в прошлом году."

Вопрос: "А сколько ей лет?"
Ответ: "Айгуль 28 лет, родилась 15 марта 1996 года."

Вопрос: "У неё есть активная подписка?"
Ответ: "Да, у Айгуль активная подписка Hero's Pass, которая действует до 15 декабря 2024."

Вопрос: "А кто на втором месте?"
Ответ: "На втором месте Ержан Кенжебаев с 132 посещениями. Он тренируется в клубе Сатпаева."

Вопрос: "Покажи их email"
[Если email есть в данных]
Ответ: "Email Айгуль: aigul.smagulova@gmail.com. Если нужны контакты других пользователей из топа, могу сгенерировать таблицу."

[Если email нет в данных]
Ответ: "К сожалению, email нет в текущих данных. Если нужна эта информация, могу сделать новый запрос с контактами пользователей."

**Стиль:**
- На русском языке
- Дружелюбный но профессиональный
- Конкретные цифры и факты
- Минимум эмодзи (только если очень уместно)
- Как ChatGPT в режиме разговора"""

    def answer_followup(
        self,
        user_question: str,
        previous_dataframe: pd.DataFrame,
        previous_sql: str,
        previous_analysis: str,
        conversation_history: List[Dict]
    ) -> str:
        """
        Answer follow-up question using data in memory.

        Args:
            user_question: User's follow-up question
            previous_dataframe: DataFrame from previous query
            previous_sql: SQL query that was executed
            previous_analysis: Previous analysis text
            conversation_history: Full conversation history

        Returns:
            Natural language answer
        """
        try:
            logger.info(f"Answering follow-up: '{user_question[:100]}'")
            logger.info(f"DataFrame shape: {previous_dataframe.shape}")

            # Build context from data
            data_context = self._build_data_context(
                previous_dataframe,
                previous_sql,
                previous_analysis
            )

            # Build conversation context
            conversation_context = self._build_conversation_context(conversation_history)

            # Create prompt
            user_prompt = f"""**Данные из предыдущего запроса:**
{data_context}

**История разговора:**
{conversation_context}

**Новый вопрос пользователя:**
{user_question}

Ответь на вопрос естественно, используя данные выше."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,  # Slightly more creative for natural conversation
                max_tokens=500
            )

            answer = response.choices[0].message.content.strip()
            logger.info(f"Generated follow-up answer ({len(answer)} chars)")

            return answer

        except Exception as e:
            logger.error(f"Error in continuation agent: {e}")
            return "Извините, произошла ошибка при обработке вашего вопроса. Попробуйте переформулировать или задать новый запрос."

    def _build_data_context(
        self,
        df: pd.DataFrame,
        sql: str,
        analysis: str
    ) -> str:
        """
        Build readable data context from DataFrame.

        Args:
            df: DataFrame with data
            sql: SQL query
            analysis: Previous analysis

        Returns:
            Formatted context string
        """
        # DataFrame preview (first 20 rows)
        preview_rows = min(20, len(df))
        df_preview = df.head(preview_rows).to_string(index=False, max_colwidth=50)

        context_parts = [
            f"SQL запрос: {sql[:300]}..." if len(sql) > 300 else f"SQL запрос: {sql}",
            "",
            f"Результаты ({len(df)} записей, показываю первые {preview_rows}):",
            df_preview,
            "",
            f"Колонки: {', '.join(df.columns.tolist())}",
            f"Количество записей: {len(df)}",
            ""
        ]

        # Add data types for context
        if len(df) > 0:
            dtypes_str = ", ".join([f"{col}: {dtype}" for col, dtype in df.dtypes.items()])
            context_parts.append(f"Типы данных: {dtypes_str}")
            context_parts.append("")

        # Add previous analysis for context
        if analysis:
            # Take first 500 chars of analysis
            analysis_preview = analysis[:500] + "..." if len(analysis) > 500 else analysis
            context_parts.append("Предыдущий анализ:")
            context_parts.append(analysis_preview)

        return "\n".join(context_parts)

    def _build_conversation_context(self, history: List[Dict]) -> str:
        """
        Build conversation context from history.

        Args:
            history: Conversation messages

        Returns:
            Formatted conversation string
        """
        if not history:
            return "Нет предыдущих сообщений"

        # Get last 8 messages (4 exchanges)
        recent = history[-8:] if len(history) > 8 else history

        lines = []
        for msg in recent:
            role = "👤 Пользователь" if msg["role"] == "user" else "🤖 Бот"
            content = msg["content"][:200]  # Truncate
            if len(msg["content"]) > 200:
                content += "..."
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def should_offer_table(self, question: str, df_size: int) -> bool:
        """
        Determine if we should offer to generate a table.

        Args:
            question: User question
            df_size: Number of rows in DataFrame

        Returns:
            True if should offer table generation
        """
        # Offer table if:
        # 1. DataFrame is large (>20 rows)
        # 2. Question explicitly asks for list/table
        # 3. Question asks for multiple items

        if df_size > 20:
            return True

        question_lower = question.lower()

        # Keywords suggesting they want multiple results
        list_keywords = ["все", "список", "покажи всех", "выгрузи", "таблиц", "данные"]
        if any(keyword in question_lower for keyword in list_keywords):
            return True

        return False
