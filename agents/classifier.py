"""
Query Classifier Agent
Classifies user queries into different types: informational or data extraction
"""
from typing import Literal
from anthropic import Anthropic
from utils.logger import setup_logger

logger = setup_logger(__name__, "INFO")

QueryType = Literal["informational", "data_extraction", "follow_up"]


class QueryClassifier:
    """Classifies user queries to route them to appropriate agents."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        """
        Initialize classifier.

        Args:
            api_key: Anthropic API key
            model: Model to use for classification
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model

        self.system_prompt = """Ты классификатор запросов для Hero's Journey SQL Assistant.

Твоя задача - определить тип запроса пользователя:

1. **informational** - информационные вопросы:
   - Вопросы о функционале бота
   - Вопросы о Hero's Journey (что это, описание)
   - Общие вопросы о возможностях системы
   - Примеры запросов которые можно делать

   Примеры:
   - "Что ты умеешь?"
   - "Расскажи о своем функционале"
   - "Что такое Hero's Journey?"
   - "Какие данные ты можешь выгрузить?"
   - "Помоги мне сформулировать запрос"

2. **data_extraction** - запросы на выгрузку данных:
   - Любые запросы о получении данных из БД
   - Запросы на выгрузку списков пользователей
   - Аналитические запросы
   - Запросы со словами "выведи", "покажи", "выгрузи", "сколько", "кто", "какие"

   Примеры:
   - "Выведи действующих триальщиков"
   - "Сколько пользователей с активной подпиской?"
   - "Покажи юзеров у кого заканчивается ХП абонемент в ближайшие 7 дней"
   - "Список участников марафона"

3. **follow_up** - уточнение или продолжение предыдущего запроса:
   - Ссылки на предыдущий результат ("а теперь", "ещё", "добавь", "разбей")
   - Модификация предыдущего запроса ("только по Алматы", "за прошлый месяц")
   - Короткие уточнения без полного контекста ("по клубам", "с email")

   Примеры:
   - "а теперь разбей по клубам"
   - "добавь колонку с email"
   - "за прошлый месяц"
   - "только по Алматы"
   - "а сколько из них активных?"

   ВАЖНО: follow_up возможен ТОЛЬКО если предоставлен контекст предыдущего разговора.
   Без контекста такие запросы классифицируй как data_extraction.

ВАЖНО: Отвечай ТОЛЬКО одним словом: "informational", "data_extraction" или "follow_up" без каких-либо объяснений."""

    def classify(self, user_query: str, conversation_context: dict = None) -> QueryType:
        """
        Classify user query, optionally using conversation context.

        Args:
            user_query: User's question
            conversation_context: Optional dict with previous conversation context
                - previous_question: Last user question
                - previous_sql: Last SQL query
                - history: List of recent interactions

        Returns:
            Query type: 'informational', 'data_extraction', or 'follow_up'
        """
        try:
            logger.info(f"Classifying query: {user_query[:100]}")

            # Build input with context if available
            classify_input = user_query
            if conversation_context and conversation_context.get("previous_question"):
                classify_input = (
                    f"Предыдущий запрос пользователя: {conversation_context['previous_question']}\n"
                    f"Текущий запрос: {user_query}"
                )

            response = self.client.messages.create(
                model=self.model,
                system=self.system_prompt,
                messages=[
                    {"role": "user", "content": classify_input}
                ],
                temperature=0,
                max_tokens=50
            )

            classification = response.content[0].text.strip().lower()

            # Validate response
            valid_types = ["informational", "data_extraction", "follow_up"]
            if classification not in valid_types:
                logger.warning(f"Unexpected classification: {classification}, defaulting to data_extraction")
                return "data_extraction"

            # follow_up without context should be treated as data_extraction
            if classification == "follow_up" and not conversation_context:
                logger.info("follow_up without context, treating as data_extraction")
                return "data_extraction"

            logger.info(f"Query classified as: {classification}")
            return classification

        except Exception as e:
            logger.error(f"Classification error: {e}")
            return "data_extraction"
