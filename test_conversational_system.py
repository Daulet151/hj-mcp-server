"""
Test script for the new conversational system
"""
import sys
import pandas as pd
from agents import AgentOrchestrator, SmartIntentClassifier, ContinuationAgent, ConversationContext
from config import Config

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Mock components for testing
class MockSQLGenerator:
    def generate_sql(self, query, schema_docs):
        return "SELECT * FROM users LIMIT 10"

class MockDBManager:
    def execute_query(self, sql):
        # Return mock DataFrame
        return pd.DataFrame({
            'id': ['678321651', '123456789'],
            'firstname': ['Айгуль', 'Ержан'],
            'lastname': ['Смагулова', 'Кенжебаев'],
            'age': [28, 32],
            'visits': [145, 132],
            'email': ['aigul@example.com', 'erzhan@example.com']
        })

def test_conversational_flow():
    """Test the complete conversational flow."""
    print("=" * 80)
    print("TESTING CONVERSATIONAL AI SYSTEM")
    print("=" * 80)

    # Initialize orchestrator
    schema_docs = {"tables": {}}  # Empty for test
    sql_gen = MockSQLGenerator()
    db_manager = MockDBManager()

    orchestrator = AgentOrchestrator(
        api_key=Config.OPENAI_API_KEY,
        schema_docs=schema_docs,
        sql_generator=sql_gen,
        db_manager=db_manager,
        model=Config.OPENAI_MODEL
    )

    # Simulate conversation
    user_id = "U12345"
    channel_id = "C67890"

    print("\n" + "=" * 80)
    print("Test Scenario: User asks analytical question, then follow-ups")
    print("=" * 80)

    # Message 1: Data query
    print("\n[User]: Кто больше всех ходил на тренировки в прошлом году?")
    response, should_gen_table, data, query, qtype = orchestrator.process_message(
        "Кто больше всех ходил на тренировки в прошлом году?",
        user_id,
        channel_id
    )
    print(f"\n[Bot]: {response[:200]}...")
    print(f"[System] Query type: {qtype}, Should generate table: {should_gen_table}")

    # Message 2: Follow-up question (should use continuation agent)
    print("\n" + "-" * 80)
    print("\n[User]: Как зовут этого юзера?")
    response, should_gen_table, data, query, qtype = orchestrator.process_message(
        "Как зовут этого юзера?",
        user_id,
        channel_id
    )
    print(f"\n[Bot]: {response}")
    print(f"[System] Query type: {qtype}, Should generate table: {should_gen_table}")

    # Message 3: Another follow-up
    print("\n" + "-" * 80)
    print("\n[User]: А сколько ей лет?")
    response, should_gen_table, data, query, qtype = orchestrator.process_message(
        "А сколько ей лет?",
        user_id,
        channel_id
    )
    print(f"\n[Bot]: {response}")
    print(f"[System] Query type: {qtype}, Should generate table: {should_gen_table}")

    # Message 4: Request table
    print("\n" + "-" * 80)
    print("\n[User]: Сгенерируй таблицу")
    response, should_gen_table, data, query, qtype = orchestrator.process_message(
        "Сгенерируй таблицу",
        user_id,
        channel_id
    )
    print(f"\n[Bot]: {response}")
    print(f"[System] Query type: {qtype}, Should generate table: {should_gen_table}")

    if should_gen_table and data:
        print(f"[System] Table data ready: {len(data['dataframe'])} rows")
        print(f"[System] SQL: {data['sql_query']}")

    # Check context
    print("\n" + "=" * 80)
    print("CONTEXT SUMMARY")
    print("=" * 80)
    summary = orchestrator.get_context_summary(user_id, channel_id)
    if summary:
        for key, value in summary.items():
            print(f"{key}: {value}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


def test_smart_classifier():
    """Test the smart classifier with context."""
    print("\n" + "=" * 80)
    print("TESTING SMART CLASSIFIER")
    print("=" * 80)

    classifier = SmartIntentClassifier(
        api_key=Config.OPENAI_API_KEY,
        model=Config.OPENAI_MODEL
    )

    test_cases = [
        {
            "message": "Как зовут этого юзера?",
            "history": [
                {"role": "user", "content": "Кто больше ходил на тренировки?"},
                {"role": "assistant", "content": "Юзер ID 678321651 с 145 посещениями"}
            ],
            "has_data": True,
            "expected": "continuation"
        },
        {
            "message": "да",
            "history": [
                {"role": "user", "content": "Кто больше ходил?"},
                {"role": "assistant", "content": "... Сгенерировать таблицу?"}
            ],
            "has_data": True,
            "expected": "table_request"
        },
        {
            "message": "Покажи пользователей с подпиской",
            "history": [],
            "has_data": False,
            "expected": "new_data_query"
        },
        {
            "message": "Что ты умеешь?",
            "history": [],
            "has_data": False,
            "expected": "informational"
        }
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}:")
        print(f"  Message: '{test['message']}'")
        print(f"  History: {len(test['history'])} msgs")
        print(f"  Has data: {test['has_data']}")

        intent = classifier.classify_with_context(
            user_message=test['message'],
            conversation_history=test['history'],
            has_pending_data=test['has_data']
        )

        print(f"  Result: {intent}")
        print(f"  Expected: {test['expected']}")
        print(f"  ✓ PASS" if intent == test['expected'] else f"  ✗ FAIL")


def test_conversation_context():
    """Test conversation context storage."""
    print("\n" + "=" * 80)
    print("TESTING CONVERSATION CONTEXT")
    print("=" * 80)

    context = ConversationContext(timeout_minutes=30)

    # Add messages
    context.add_user_message("Привет, покажи пользователей")
    context.add_bot_message("Конечно! Нашёл 100 пользователей...")
    context.add_user_message("Как зовут первого?")
    context.add_bot_message("Это Айгуль Смагулова")

    # Save data
    df = pd.DataFrame({'id': [1, 2], 'name': ['Айгуль', 'Ержан']})
    context.save_data(df, "SELECT * FROM users", "Анализ пользователей")

    print(f"\nContext summary:")
    summary = context.get_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")

    print(f"\nHas dataframe: {context.has_dataframe()}")
    print(f"History size: {len(context.history)}")
    print(f"Recent history (2 msgs):")
    for msg in context.get_recent_history(2):
        print(f"  {msg['role']}: {msg['content'][:50]}...")

    print(f"\n✓ Context test passed")


if __name__ == "__main__":
    try:
        # Run tests
        test_conversation_context()
        print("\n")
        # test_smart_classifier()  # Uncomment if you want to test classifier with API
        # test_conversational_flow()  # Uncomment for full flow test

        print("\n" + "=" * 80)
        print("ALL TESTS COMPLETE!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
