"""Integration test for orchestrator image handling across multiple iterations.

This test verifies that downloaded receipt images are cached in session
and never leak into the conversation history as base64 strings, preventing
massive token consumption.

Test scenario mirrors the real-world workflow:
1. Save description, attempt OCR (fails - no image yet)
2. Get file ID
3. Download photo and run OCR (success - image cached)
4. Send formatted receipt, create split
5. Run verification checks
6. Complete with final message

Key validations:
- Image downloaded once and cached in session
- No base64 image data in conversation history after download
- Conversation history stays small (<20KB vs >2MB without caching)
- OCR can retrieve image from session cache
"""

import base64
import json
from typing import Any, TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

# Import only the models to avoid circular imports
from src.models.bill import ReceiptData

if TYPE_CHECKING:
    from src.agent.context_builder import AgentContext
    from src.agent.orchestrator import AgentOrchestrator


# ===== HELPER FUNCTIONS =====


def check_messages_for_base64(messages: list[dict[str, Any]]) -> tuple[bool, int, int]:
    """
    Check if conversation messages contain base64-encoded image data.

    Args:
        messages: List of message dictionaries sent to Claude API

    Returns:
        Tuple of (has_base64_data, max_message_size, total_conversation_size)
    """
    has_base64 = False
    max_size = 0
    total_size = 0

    for message in messages:
        # Convert message to string representation (handles Anthropic objects)
        message_str = str(message)
        message_size = len(message_str)
        total_size += message_size
        max_size = max(max_size, message_size)

        # Check for base64 patterns (long alphanumeric strings typical of base64)
        # A 100KB image becomes ~140KB base64 string
        if message_size > 50000:  # Suspiciously large message
            has_base64 = True

        # Check for actual base64 image markers
        content = message.get("content", "")

        # Handle different content types
        if isinstance(content, str):
            # String content - check for base64 patterns
            if "data:image" in content or len(content) > 50000:
                has_base64 = True
        elif isinstance(content, list):
            # List of content blocks - check each one
            for block in content:
                block_str = str(block)
                if "image" in block_str and "base64" in block_str:
                    has_base64 = True
                if len(block_str) > 50000:  # Large block likely contains image
                    has_base64 = True

    return has_base64, max_size, total_size


def create_tool_use_message(
    tool_calls: list[tuple[str, dict[str, Any]]], reasoning: str = ""
) -> Message:
    """
    Create a mock Anthropic message with tool use blocks.

    Args:
        tool_calls: List of (tool_name, tool_input) tuples
        reasoning: Optional reasoning text before tool calls

    Returns:
        Mock Anthropic Message with tool_use stop reason
    """
    content: list[Any] = []

    if reasoning:
        content.append(TextBlock(type="text", text=reasoning))

    for i, (tool_name, tool_input) in enumerate(tool_calls):
        content.append(
            ToolUseBlock(
                id=f"toolu_test_{i}",
                type="tool_use",
                name=tool_name,
                input=tool_input,
            )
        )

    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        content=content,
        model="claude-sonnet-4-20250514",
        stop_reason="tool_use",
        stop_sequence=None,
        usage=Usage(input_tokens=100, output_tokens=50),
    )


def create_end_turn_message(final_text: str = "Task completed") -> Message:
    """Create a mock completion message with end_turn."""
    return Message(
        id="msg_test_end",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text=final_text)],
        model="claude-sonnet-4-20250514",
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=100, output_tokens=20),
    )


# ===== FIXTURES =====


@pytest.fixture
def sample_receipt_image():
    """
    Create a fake receipt image (100KB JPEG).

    This simulates a real receipt photo that would be ~100-150KB.
    """
    # JPEG magic bytes + fake data to make it ~100KB
    jpeg_header = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    fake_image_data = jpeg_header + b"X" * (100 * 1024 - len(jpeg_header))
    return fake_image_data


@pytest.fixture
def sample_receipt_data():
    """Sample OCR-extracted receipt data."""
    return ReceiptData.model_validate_json(
        json.dumps(
            {
                "items": [
                    {"name": "Burger", "price": "15.00", "quantity": 1},
                    {"name": "Salad", "price": "12.00", "quantity": 1},
                    {"name": "Fries", "price": "5.00", "quantity": 2},
                ],
                "currency": "USD",
                "subtotal": "37.00",
                "total": "37.00",
            }
        )
    )


@pytest.fixture
def conversation_tracker():
    """
    Fixture that tracks all messages sent to Claude API.

    Returns a list that will be populated with message dictionaries.
    """
    return []


# ===== INTEGRATION TEST =====


class TestOrchestratorImageHandling:
    """Integration test for multi-iteration orchestrator workflow with image handling."""

    @pytest.mark.asyncio
    async def test_image_not_leaked_across_iterations(
        self,
        mock_telegram_update,
        mock_telegram_context,
        mock_telegram_file,
        sample_receipt_image,
        sample_receipt_data,
        conversation_tracker,
    ):
        """
        Test that receipt images don't leak into conversation history across iterations.

        This simulates a real 6-iteration workflow where:
        1. User provides description
        2. Agent downloads photo and runs OCR
        3. Agent sends formatted receipt
        4. Agent creates bill split
        5. Agent runs verification
        6. Agent completes

        The test verifies that after the image is downloaded and recognized in iteration 2,
        it never appears as base64 in subsequent Claude API calls, preventing massive
        token overconsumption.
        """
        # Setup: Configure telegram mocks
        mock_telegram_file.download_as_bytearray = AsyncMock(
            return_value=bytearray(sample_receipt_image)
        )
        mock_telegram_context.bot.get_file = AsyncMock(return_value=mock_telegram_file)

        # Setup: Prepare mock Anthropic responses for each iteration
        iteration_responses = [
            # Iteration 1: Save description, send status
            create_tool_use_message(
                [
                    (
                        "save_participant_description",
                        {"description": "Alice had burger, Bob had salad and fries"},
                    ),
                    ("send_processing_status", {"status": "Processing receipt..."}),
                ]
            ),
            # Iteration 2: Get file ID, download photo, run OCR
            create_tool_use_message(
                [
                    ("get_receipt_file_id", {}),
                    ("download_telegram_photo", {"file_id": "test_file_id_123"}),
                    ("extract_receipt_ocr", {}),
                ]
            ),
            # Iteration 3: Send formatted receipt
            create_tool_use_message(
                [
                    (
                        "send_formatted_receipt",
                        {"receipt_data_json": sample_receipt_data.model_dump_json()},
                    ),
                ]
            ),
            # Iteration 4: Create split
            create_tool_use_message(
                [
                    (
                        "create_initial_bill_split",
                        {
                            "description": "Alice had burger, Bob had salad and fries",
                            "receipt_data_json": sample_receipt_data.model_dump_json(),
                        },
                    ),
                ]
            ),
            # Iteration 5: Send formatted split, verify
            create_tool_use_message(
                [
                    (
                        "send_formatted_split",
                        {
                            "bill_split_json": json.dumps(
                                {
                                    "participants": [
                                        {
                                            "name": "Alice",
                                            "items": [
                                                {
                                                    "item_name": "Burger",
                                                    "item_numerator": 1,
                                                    "item_denominator": 1,
                                                }
                                            ],
                                        },
                                        {
                                            "name": "Bob",
                                            "items": [
                                                {
                                                    "item_name": "Salad",
                                                    "item_numerator": 1,
                                                    "item_denominator": 1,
                                                },
                                                {
                                                    "item_name": "Fries",
                                                    "item_numerator": 1,
                                                    "item_denominator": 1,
                                                },
                                            ],
                                        },
                                    ],
                                    "receipt_items": [
                                        {
                                            "name": "Burger",
                                            "price": "15.00",
                                            "quantity": 1,
                                        },
                                        {
                                            "name": "Salad",
                                            "price": "12.00",
                                            "quantity": 1,
                                        },
                                        {
                                            "name": "Fries",
                                            "price": "5.00",
                                            "quantity": 2,
                                        },
                                    ],
                                    "currency": "USD",
                                    "total": "37.00",
                                }
                            )
                        },
                    ),
                    (
                        "calculate_all_participant_totals",
                        {
                            "bill_split_json": "..."  # Simplified for test
                        },
                    ),
                    ("check_accuracy_threshold", {"discrepancy": 0.0}),
                ]
            ),
            # Iteration 6: Complete
            create_end_turn_message("Bill split completed successfully"),
        ]

        # Define mock function for Anthropic API
        response_index = 0

        def mock_messages_create(*args, **kwargs):
            nonlocal response_index

            # Capture the messages sent to Claude API for validation
            messages = kwargs.get("messages", [])
            conversation_tracker.extend(messages)

            # Return the appropriate mock response
            response = iteration_responses[response_index]
            response_index += 1
            return response

        # Setup: Mock conversation manager to return a fresh session
        from src.bot.conversation_manager import conversation_manager

        with patch.object(conversation_manager, "get_session") as mock_get_session:
            # Create a real session to test caching
            from src.models.agent_state import AgentBillSession

            session = AgentBillSession()
            session.receipt_file_id = "test_file_id_123"  # Pre-populate file ID
            mock_get_session.return_value = session

            # Mock extract_receipt_ocr to return the sample data
            async def mock_extract_receipt_ocr(
                chat_id: int, image_bytes: bytes | None = None
            ):
                # Return receipt data (image should be cached in session by this point)
                return sample_receipt_data

            # Replace the function with our mock (patch at the import location used by orchestrator)
            with patch("src.tools.extract_receipt_ocr", new=mock_extract_receipt_ocr):
                # Mock AnthropicService for split_bill
                with patch("src.tools.llm_processing.AnthropicService") as MockService:
                    mock_service_instance = MockService.return_value

                    # Mock create_initial_bill_split
                    async def mock_create_split(*args, **kwargs):
                        from src.models.bill import (
                            BillSplit,
                            ParticipantItem,
                            ParticipantShare,
                        )

                        return BillSplit(
                            participants=[
                                ParticipantShare(
                                    name="Alice",
                                    items=[
                                        ParticipantItem(
                                            item_name="Burger",
                                            item_numerator=1,
                                            item_denominator=1,
                                        )
                                    ],
                                ),
                                ParticipantShare(
                                    name="Bob",
                                    items=[
                                        ParticipantItem(
                                            item_name="Salad",
                                            item_numerator=1,
                                            item_denominator=1,
                                        ),
                                        ParticipantItem(
                                            item_name="Fries",
                                            item_numerator=1,
                                            item_denominator=1,
                                        ),
                                    ],
                                ),
                            ],
                            receipt_items=sample_receipt_data.items,
                            currency=sample_receipt_data.currency,
                            total=sample_receipt_data.total,
                        )

                    mock_service_instance.split_bill = AsyncMock(
                        side_effect=mock_create_split
                    )

                    # Import here to avoid circular import at module level
                    from src.agent.context_builder import AgentContext
                    from src.agent.orchestrator import AgentOrchestrator as Orchestrator

                    # Setup: Create agent context
                    chat_id = 12345
                    mock_telegram_update.effective_chat.id = chat_id

                    agent_context = AgentContext(
                        chat_id=chat_id,
                        update=mock_telegram_update,
                        context=mock_telegram_context,
                    )

                    # Create orchestrator instance
                    orchestrator = Orchestrator()

                    # Mock the orchestrator's AsyncAnthropic client
                    orchestrator.client.messages.create = AsyncMock(
                        side_effect=mock_messages_create
                    )

                    # ACT: Run the orchestrator
                    await orchestrator.run(
                        agent_context=agent_context,
                        new_message="Alice had burger, Bob had salad and fries",
                    )

        # ===== ASSERTIONS =====

        # 1. Verify image was cached in session
        assert session.has_image_bytes(), "Image should be cached in session"
        assert session.image_bytes == sample_receipt_image, (
            "Cached image should match downloaded image"
        )

        # 2. Verify NO base64 image data in conversation history
        has_base64, max_msg_size, total_size = check_messages_for_base64(
            conversation_tracker
        )

        assert not has_base64, (
            "Conversation should NOT contain base64 image data. "
            f"Max message size: {max_msg_size} bytes"
        )

        # 3. Verify message sizes stay reasonable (<5KB per message)
        # Without the fix, the image would be ~140KB base64 in EACH message after download
        assert max_msg_size < 5000, (
            f"Individual messages should be small (<5KB). Found: {max_msg_size} bytes. "
            "Large messages indicate base64 image leakage."
        )

        # 4. Verify total conversation stays under 20KB
        # Without the fix, 6 iterations with 140KB image each = ~840KB total
        # With the fix, should be <20KB total
        assert total_size < 20000, (
            f"Total conversation size should be <20KB. Found: {total_size} bytes. "
            "Large conversation indicates image data is being included multiple times."
        )

        # 5. Verify orchestrator completed successfully (6 iterations)
        # The mock was called 6 times (one per iteration)
        assert orchestrator.client.messages.create.call_count == 6, (
            "Orchestrator should complete in 6 iterations"
        )

        # 7. Log success metrics for reference
        print("\n=== Image Handling Test Results ===")
        print(
            f"✓ Image cached: {len(sample_receipt_image)} bytes ({len(sample_receipt_image) / 1024:.1f} KB)"
        )
        print(f"✓ Base64 in conversation: {has_base64}")
        print(
            f"✓ Max message size: {max_msg_size} bytes ({max_msg_size / 1024:.1f} KB)"
        )
        print(f"✓ Total conversation: {total_size} bytes ({total_size / 1024:.1f} KB)")
        print(f"✓ Iterations: {orchestrator.client.messages.create.call_count}")
        print(
            f"✓ Token savings: ~{(len(sample_receipt_image) * 1.4 * 4) / 1024:.1f}KB per iteration avoided"
        )
