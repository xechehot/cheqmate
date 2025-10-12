"""Shared test fixtures and mocks for all tests.

This module provides:
- Mock Anthropic client with realistic responses
- Mock Telegram bot and context
- Sample data fixtures (ReceiptData, BillSplit, etc.)
- Mock conversation_manager
"""

import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from anthropic.types import (
    ContentBlock,
    Message,
    TextBlock,
    ToolUseBlock,
    Usage,
)

from src.models.agent_state import AgentBillSession
from src.models.bill import (
    BillSplit,
    ParticipantItem,
    ParticipantShare,
    ReceiptData,
    ReceiptItem,
)


# ===== SAMPLE DATA FIXTURES =====


@pytest.fixture
def sample_receipt_items():
    """Sample receipt items for testing."""
    return [
        ReceiptItem(name="Burger", price=Decimal("15.00"), quantity=1),
        ReceiptItem(name="Salad", price=Decimal("12.00"), quantity=1),
        ReceiptItem(name="Fries", price=Decimal("5.00"), quantity=2),
        ReceiptItem(name="Soda", price=Decimal("3.00"), quantity=2),
    ]


@pytest.fixture
def sample_receipt_data(sample_receipt_items):
    """Sample ReceiptData object for testing."""
    total = sum(item.total_price for item in sample_receipt_items)
    return ReceiptData(
        items=sample_receipt_items,
        currency="USD",
        subtotal=total,
        total=total,
    )


@pytest.fixture
def sample_participant_shares(sample_receipt_items):
    """Sample participant shares for testing."""
    return [
        ParticipantShare(
            name="Alice",
            items=[
                ParticipantItem(item_name="Burger", item_numerator=1, item_denominator=1),
                ParticipantItem(item_name="Fries", item_numerator=1, item_denominator=2),
                ParticipantItem(item_name="Soda", item_numerator=1, item_denominator=2),
            ],
        ),
        ParticipantShare(
            name="Bob",
            items=[
                ParticipantItem(item_name="Salad", item_numerator=1, item_denominator=1),
                ParticipantItem(item_name="Fries", item_numerator=1, item_denominator=2),
                ParticipantItem(item_name="Soda", item_numerator=1, item_denominator=2),
            ],
        ),
    ]


@pytest.fixture
def sample_bill_split(sample_receipt_items, sample_participant_shares):
    """Sample BillSplit object for testing."""
    total = sum(item.total_price for item in sample_receipt_items)
    return BillSplit(
        participants=sample_participant_shares,
        receipt_items=sample_receipt_items,
        currency="USD",
        total=total,
    )


# ===== MOCK TELEGRAM FIXTURES =====


@pytest.fixture
def mock_telegram_update():
    """Mock Telegram Update object."""
    update = Mock()
    update.effective_chat = Mock()
    update.effective_chat.id = 12345
    update.message = Mock()
    update.message.text = "Test message"
    update.message.photo = []
    return update


@pytest.fixture
def mock_telegram_context():
    """Mock Telegram context with bot."""
    context = Mock()
    context.bot = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.get_file = AsyncMock()
    return context


@pytest.fixture
def mock_telegram_file():
    """Mock Telegram File object for photo download."""
    file = AsyncMock()
    file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake_image_data"))
    return file


# ===== MOCK ANTHROPIC CLIENT FIXTURES =====


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client that returns realistic responses."""
    client = Mock()
    client.messages = Mock()
    client.messages.create = Mock()
    return client


@pytest.fixture
def mock_anthropic_message_end_turn():
    """Mock Anthropic message with end_turn stop reason (task complete)."""
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text="Task completed successfully")],
        model="claude-sonnet-4-20250514",
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=100, output_tokens=50),
    )


@pytest.fixture
def mock_anthropic_message_with_tool_use():
    """Mock Anthropic message with tool use."""

    def create_tool_use_message(tool_name: str, tool_input: dict[str, Any]):
        return Message(
            id="msg_test",
            type="message",
            role="assistant",
            content=[
                TextBlock(type="text", text=f"I will use the {tool_name} tool"),
                ToolUseBlock(
                    id="tool_test_123",
                    type="tool_use",
                    name=tool_name,
                    input=tool_input,
                ),
            ],
            model="claude-sonnet-4-20250514",
            stop_reason="tool_use",
            stop_sequence=None,
            usage=Usage(input_tokens=100, output_tokens=50),
        )

    return create_tool_use_message


@pytest.fixture
def mock_ocr_response():
    """Mock OCR response JSON."""
    return {
        "currency": "USD",
        "items": [
            {"name": "Burger", "price": 15.00, "quantity": 1},
            {"name": "Salad", "price": 12.00, "quantity": 1},
            {"name": "Fries", "price": 5.00, "quantity": 2},
        ],
        "subtotal": 37.00,
        "total": 37.00,
    }


@pytest.fixture
def mock_split_response():
    """Mock bill split response JSON."""
    return {
        "participants": [
            {
                "name": "Alice",
                "items": [
                    {"item_name": "Burger", "item_numerator": 1, "item_denominator": 1},
                    {"item_name": "Fries", "item_numerator": 1, "item_denominator": 2},
                ],
            },
            {
                "name": "Bob",
                "items": [
                    {"item_name": "Salad", "item_numerator": 1, "item_denominator": 1},
                    {"item_name": "Fries", "item_numerator": 1, "item_denominator": 2},
                ],
            },
        ]
    }


# ===== MOCK SESSION FIXTURES =====


@pytest.fixture
def mock_agent_session():
    """Mock AgentBillSession for testing."""
    session = AgentBillSession()
    session.reset()
    return session


@pytest.fixture
def mock_conversation_manager(mock_agent_session):
    """Mock conversation manager."""
    manager = Mock()
    manager.get_session = Mock(return_value=mock_agent_session)
    return manager


# ===== HELPER FUNCTIONS =====


def create_mock_anthropic_response(content_text: str, stop_reason: str = "end_turn"):
    """Helper to create mock Anthropic API responses."""
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text=content_text)],
        model="claude-sonnet-4-20250514",
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=100, output_tokens=50),
    )
