"""
Query Classifier Agent
Classifies user queries into different types: informational or data extraction
"""
from typing import Literal
from openai import OpenAI
from utils.logger import setup_logger

logger = setup_logger(__name__, "INFO")

QueryType = Literal["informational", "data_extraction"]


class QueryClassifier:
    """Classifies user queries to route them to appropriate agents."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        Initialize classifier.

        Args:
            api_key: OpenAI API key
            model: Model to use for classification
        """
        self.client = OpenAI(api_key=api_key)
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

ВАЖНО: Отвечай ТОЛЬКО одним словом: "informational" или "data_extraction" без каких-либо объяснений."""

    def classify(self, user_query: str) -> QueryType:
        """
        Classify user query.

        Args:
            user_query: User's question

        Returns:
            Query type: 'informational' or 'data_extraction'
        """
        try:
            logger.info(f"Classifying query: {user_query[:100]}")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0,
                max_tokens=10
            )

            classification = response.choices[0].message.content.strip().lower()

            # Validate response
            if classification not in ["informational", "data_extraction"]:
                logger.warning(f"Unexpected classification: {classification}, defaulting to data_extraction")
                return "data_extraction"

            logger.info(f"Query classified as: {classification}")
            return classification

        except Exception as e:
            logger.error(f"Classification error: {e}")
            # Default to data_extraction on error
            return "data_extraction"
