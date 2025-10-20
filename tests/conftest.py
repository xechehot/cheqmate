"""Pytest configuration and shared fixtures for CheqMate tests."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Message, PhotoSize, Update, User

from src.models.bill import BillSplit, ParticipantShare, Receipt, ReceiptItem


@pytest.fixture
def sample_receipt_usd() -> Receipt:
    """Create a sample receipt in USD for testing."""
    return Receipt(
        restaurant_name="Test Restaurant",
        restaurant_address="123 Main St, City, State",
        currency="USD",
        items=[
            ReceiptItem(
                description="Burger",
                quantity=1,
                line_total=Decimal("15.00"),
                unit_price=Decimal("15.00"),
            ),
            ReceiptItem(
                description="Salad",
                quantity=1,
                line_total=Decimal("12.00"),
                unit_price=Decimal("12.00"),
            ),
            ReceiptItem(
                description="Pasta",
                quantity=1,
                line_total=Decimal("18.00"),
                unit_price=Decimal("18.00"),
            ),
        ],
        total=Decimal("45.00"),
    )


@pytest.fixture
def sample_receipt_kzt() -> Receipt:
    """Create a sample receipt in KZT for testing."""
    return Receipt(
        restaurant_name="Almaty Cafe",
        restaurant_address="10 Abay Avenue, Almaty",
        currency="KZT",
        items=[
            ReceiptItem(
                description="Beshbarmak",
                quantity=1,
                line_total=Decimal("3500"),
                unit_price=Decimal("3500"),
            ),
            ReceiptItem(
                description="Lagman",
                quantity=2,
                line_total=Decimal("4000"),
                unit_price=Decimal("2000"),
            ),
            ReceiptItem(
                description="Tea",
                quantity=3,
                line_total=Decimal("900"),
                unit_price=Decimal("300"),
            ),
        ],
        total=Decimal("8400"),
    )


@pytest.fixture
def sample_bill_split_usd(sample_receipt_usd: Receipt) -> BillSplit:
    """Create a sample bill split for testing."""
    participants = [
        ParticipantShare(
            name="Alice", items=["Burger"], amount=Decimal("15.00")
        ),
        ParticipantShare(
            name="Bob", items=["Salad"], amount=Decimal("12.00")
        ),
        ParticipantShare(
            name="Charlie", items=["Pasta"], amount=Decimal("18.00")
        ),
    ]
    return BillSplit(participants=participants, receipt=sample_receipt_usd)


@pytest.fixture
def mock_anthropic_receipt_response_usd() -> dict:
    """Mock Anthropic API response for receipt extraction (USD)."""
    return {
        "restaurant_name": "Test Restaurant",
        "restaurant_address": "123 Main St, City, State",
        "currency": "USD",
        "items": [
            {
                "description": "Burger",
                "quantity": 1,
                "line_total": 15.00,
                "unit_price": 15.00,
            },
            {"description": "Salad", "quantity": 1, "line_total": 12.00},
            {"description": "Pasta", "quantity": 1, "line_total": 18.00},
        ],
        "total": 45.00,
    }


@pytest.fixture
def mock_anthropic_receipt_response_kzt() -> dict:
    """Mock Anthropic API response for receipt extraction (KZT)."""
    return {
        "restaurant_name": "Almaty Cafe",
        "restaurant_address": "10 Abay Avenue, Almaty",
        "currency": "KZT",
        "items": [
            {
                "description": "Beshbarmak",
                "quantity": 1,
                "line_total": 3500,
                "unit_price": 3500,
            },
            {
                "description": "Lagman",
                "quantity": 2,
                "line_total": 4000,
                "unit_price": 2000,
            },
            {
                "description": "Tea",
                "quantity": 3,
                "line_total": 900,
                "unit_price": 300,
            },
        ],
        "total": 8400,
    }


@pytest.fixture
def mock_anthropic_split_response() -> dict:
    """Mock Anthropic API response for bill splitting."""
    return {
        "participants": [
            {"name": "Alice", "items": ["Burger"], "amount": 15.00},
            {"name": "Bob", "items": ["Salad"], "amount": 12.00},
            {"name": "Charlie", "items": ["Pasta"], "amount": 18.00},
        ]
    }


@pytest.fixture
def mock_telegram_user() -> User:
    """Create a mock Telegram user."""
    return User(
        id=123456789,
        first_name="Test",
        last_name="User",
        username="testuser",
        is_bot=False,
    )


@pytest.fixture
def mock_telegram_chat() -> Chat:
    """Create a mock Telegram chat."""
    return Chat(id=987654321, type="private")


@pytest.fixture
def mock_telegram_message(
    mock_telegram_user: User, mock_telegram_chat: Chat
) -> Message:
    """Create a mock Telegram message."""
    message = MagicMock(spec=Message)
    message.message_id = 1
    message.date = None
    message.chat = mock_telegram_chat
    message.from_user = mock_telegram_user
    message.text = None
    message.photo = None
    message.reply_text = AsyncMock()
    message.delete = AsyncMock()
    return message


@pytest.fixture
def mock_telegram_photo_message(
    mock_telegram_message: Message,
) -> Message:
    """Create a mock Telegram message with a photo."""
    photo = MagicMock(spec=PhotoSize)
    photo.file_id = "test_photo_file_id"
    photo.file_unique_id = "unique_id"
    photo.width = 1024
    photo.height = 768
    photo.file_size = 50000

    mock_telegram_message.photo = [photo]
    return mock_telegram_message


@pytest.fixture
def mock_telegram_text_message(
    mock_telegram_message: Message,
) -> Message:
    """Create a mock Telegram message with text."""
    mock_telegram_message.text = (
        "I had the burger, Bob had the salad, and Charlie had the pasta"
    )
    return mock_telegram_message


@pytest.fixture
def mock_telegram_update(mock_telegram_message: Message) -> Update:
    """Create a mock Telegram update."""
    update = MagicMock(spec=Update)
    update.update_id = 1
    update.message = mock_telegram_message
    update.effective_chat = mock_telegram_message.chat
    update.effective_user = mock_telegram_message.from_user
    return update


@pytest.fixture
def mock_telegram_context() -> MagicMock:
    """Create a mock Telegram context."""
    context = MagicMock()

    # Mock the bot.get_file method
    mock_file = AsyncMock()
    mock_file.download_as_bytearray = AsyncMock(
        return_value=bytearray(b"\xff\xd8\xff" + b"\x00" * 100)  # JPEG signature
    )
    context.bot.get_file = AsyncMock(return_value=mock_file)

    return context


@pytest.fixture
def sample_image_bytes() -> bytes:
    """Create sample image bytes (JPEG signature)."""
    return b"\xff\xd8\xff" + b"\x00" * 100
