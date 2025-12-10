"""
Smart Intent Classifier with Conversation Context
Classifies user messages considering conversation history and pending data
"""
from typing import List, Dict, Literal
from openai import OpenAI
from utils.logger import setup_logger

logger = setup_logger(__name__, "INFO")

IntentType = Literal["continuation", "query_refinement", "table_request", "new_data_query", "informational"]


class SmartIntentClassifier:
    """
    Classifies user intents with conversation context awareness.

    Unlike the basic classifier, this one considers:
    - Previous messages in the conversation
    - Whether there's pending data in memory
    - The context of the last query
    """

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        Initialize smart classifier.

        Args:
            api_key: OpenAI API key
            model: Model to use for classification
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model

        self.system_prompt = """Ты умный классификатор интентов с контекстом разговора для Hero's Journey AI аналитика.

Твоя задача - определить интент пользователя с учётом КОНТЕКСТА предыдущего разговора.

**5 типов интентов:**

1. **continuation** - Продолжение разговора о предыдущих данных (БЕЗ изменения SQL)
   Признаки:
   - Уточняющие вопросы: "Как зовут?", "А сколько?", "Какой возраст?"
   - Местоимения: "этого юзера", "ему", "её", "первого", "последнего"
   - Просьбы о деталях: "Расскажи подробнее", "Покажи больше информации"
   - Сравнения: "А по сравнению с прошлым годом?"

   Примеры:
   ✓ "Как зовут этого юзера?" (спрашивает имя из СУЩЕСТВУЮЩИХ данных)
   ✓ "А сколько ей лет?" (возраст уже есть в данных)
   ✓ "Покажи подробнее о первом" (детали из топа)

2. **query_refinement** - Уточнение запроса, требующее МОДИФИКАЦИИ SQL
   Признаки:
   - "из них сколько..." → нужен дополнительный фильтр/JOIN
   - "только мужчины/женщины" → добавить WHERE условие
   - "с подпиской/без подписки" → добавить JOIN с другой таблицей
   - "старше/младше N лет" → добавить фильтр
   - "в определённом городе" → добавить условие

   Примеры:
   ✓ "из них сколько имеют ХП?" (нужен JOIN с подписками)
   ✓ "только женщины" (добавить WHERE sex = 'female')
   ✓ "старше 25 лет" (добавить WHERE age > 25)
   ✓ "из Алматы" (добавить WHERE city = 'Almaty')
   ✓ "с активной подпиской" (JOIN + фильтр)

3. **table_request** - Запрос на генерацию Excel таблицы
   Признаки:
   - Явные подтверждения: "да", "yes", "давай", "ок", "конечно"
   - Просьбы о таблице: "сгенерируй", "выгрузи", "создай таблицу"
   - С модификациями: "сгенерируй только топ-5", "выгрузи имена и email"

   Примеры:
   ✓ "да"
   ✓ "давай сгенерируй"
   ✓ "сгенерируй таблицу"
   ✓ "выгрузи это в Excel"
   ✓ "хочу таблицу с топ-10"

4. **new_data_query** - НОВЫЙ запрос на выгрузку данных
   Признаки:
   - Полноценный новый запрос (не уточнение)
   - Слова: "выведи", "покажи", "сколько", "кто", "какие", "список"
   - Изменение темы разговора
   - Запрос других данных/таблиц

   Примеры:
   ✓ "Покажи пользователей с подпиской" (новая тема)
   ✓ "Сколько человек купили HeroPass на этой неделе?" (новый запрос)
   ✓ "Выведи топ по посещениям в ноябре" (другие данные)

5. **informational** - Вопросы о боте/системе
   Признаки:
   - Вопросы о функционале
   - Запросы помощи
   - Общие вопросы

   Примеры:
   ✓ "Что ты умеешь?"
   ✓ "Помощь"
   ✓ "Какие данные ты можешь показать?"

**Ключевые правила различия:**

continuation vs query_refinement:
- "Как зовут?" → continuation (ответ уже есть в данных)
- "из них сколько имеют ХП?" → query_refinement (нужен новый SQL с JOIN)

query_refinement vs new_data_query:
- "из них только женщины" → query_refinement (модификация текущего запроса)
- "покажи пользователей с подпиской" → new_data_query (совсем новый запрос)

**Формат ответа:**
Отвечай ТОЛЬКО одним словом: continuation, query_refinement, table_request, new_data_query, или informational
Никаких объяснений!"""

    def classify_with_context(
        self,
        user_message: str,
        conversation_history: List[Dict],
        has_pending_data: bool
    ) -> IntentType:
        """
        Classify user intent with conversation context.

        Args:
            user_message: Current user message
            conversation_history: Previous messages [{"role": "user/assistant", "content": "..."}]
            has_pending_data: Whether there's a DataFrame in memory from previous query

        Returns:
            Intent type: continuation, table_request, new_data_query, or informational
        """
        try:
            logger.info(f"Smart classifying: '{user_message[:80]}' | History: {len(conversation_history)} msgs | Has data: {has_pending_data}")

            # Build context for classifier
            context_info = self._build_context_string(conversation_history, has_pending_data)

            # Create prompt
            user_prompt = f"""Контекст разговора:
{context_info}

Новое сообщение пользователя: "{user_message}"

Определи интент:"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                max_tokens=10
            )

            classification = response.choices[0].message.content.strip().lower()

            # Validate response
            valid_intents = ["continuation", "query_refinement", "table_request", "new_data_query", "informational"]
            if classification not in valid_intents:
                logger.warning(f"Unexpected classification: {classification}, defaulting to new_data_query")
                return "new_data_query"

            logger.info(f"Intent classified as: {classification}")
            return classification

        except Exception as e:
            logger.error(f"Smart classification error: {e}")
            # Default to new_data_query on error (safe fallback)
            return "new_data_query"

    def _build_context_string(self, history: List[Dict], has_data: bool) -> str:
        """
        Build a readable context string from conversation history.

        Args:
            history: Conversation messages
            has_data: Whether there's pending data

        Returns:
            Formatted context string
        """
        if not history:
            return "Это первое сообщение пользователя.\nДанных в памяти: нет"

        # Get last 6 messages (3 exchanges)
        recent_history = history[-6:] if len(history) > 6 else history

        context_lines = []
        for msg in recent_history:
            role = "Пользователь" if msg["role"] == "user" else "Бот"
            content = msg["content"][:150]  # Truncate long messages
            if len(msg["content"]) > 150:
                content += "..."
            context_lines.append(f"{role}: {content}")

        context = "\n".join(context_lines)
        data_status = "ЕСТЬ (можно отвечать на уточняющие вопросы)" if has_data else "НЕТ"

        return f"""{context}

Данных в памяти: {data_status}"""

    def is_simple_confirmation(self, message: str) -> bool:
        """
        Quick check if message is a simple yes/no confirmation.
        Used as a fast path before full classification.

        Args:
            message: User message

        Returns:
            True if it's a simple confirmation
        """
        message_lower = message.lower().strip()

        # Positive confirmations
        positive = ["да", "yes", "ага", "давай", "ок", "okay", "конечно", "согласен", "+", "👍"]
        if message_lower in positive:
            return True

        # Check for "да" with punctuation
        if message_lower in ["да.", "да!", "да,", "yes.", "yes!"]:
            return True

        return False

    def is_simple_rejection(self, message: str) -> bool:
        """
        Quick check if message is a simple no/rejection.

        Args:
            message: User message

        Returns:
            True if it's a simple rejection
        """
        message_lower = message.lower().strip()

        # Negative responses
        negative = ["нет", "no", "не", "не надо", "не нужно", "отмена", "cancel", "-", "👎"]
        if message_lower in negative:
            return True

        # Check for "нет" with punctuation
        if message_lower in ["нет.", "нет!", "нет,", "no.", "no!"]:
            return True

        return False
