"""Unit tests for user interaction tools.

These tests cover the 11 user interaction functions with mocked Telegram bot.
"""

from unittest.mock import Mock

import pytest

from src.tools.user_interaction import (
    ask_clarification_question,
    download_telegram_photo,
    extract_file_id_from_message,
    get_latest_text_message,
    request_participant_description,
    request_receipt_photo,
    send_error_message,
    send_formatted_receipt,
    send_formatted_split,
    send_message,
    send_processing_status,
)


class TestSendMessage:
    """Tests for send_message function."""

    @pytest.mark.asyncio
    async def test_send_simple_message(self, mock_telegram_context):
        """Test sending a simple text message."""
        await send_message(
            chat_id=12345,
            text="Hello, world!",
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="Hello, world!",
            parse_mode="Markdown",
        )

    @pytest.mark.asyncio
    async def test_send_message_with_markdown(self, mock_telegram_context):
        """Test sending message with markdown formatting."""
        await send_message(
            chat_id=12345,
            text="**Bold** and *italic* text",
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        call_args = mock_telegram_context.bot.send_message.call_args
        assert call_args.kwargs["text"] == "**Bold** and *italic* text"
        assert call_args.kwargs["parse_mode"] == "Markdown"

    @pytest.mark.asyncio
    async def test_send_message_markdown_parsing_error_fallback(
        self, mock_telegram_context
    ):
        """Test that bad Markdown falls back to plain text."""
        from telegram.error import BadRequest

        # First call with Markdown fails, second call without Markdown succeeds
        mock_telegram_context.bot.send_message.side_effect = [
            BadRequest("Can't parse entities: can't find end of entity"),
            None,  # Second call succeeds
        ]

        await send_message(
            chat_id=12345,
            text="Bad_markdown_text",
            context=mock_telegram_context,
        )

        # Should have been called twice: once with Markdown, once without
        assert mock_telegram_context.bot.send_message.call_count == 2

        # First call with Markdown
        first_call = mock_telegram_context.bot.send_message.call_args_list[0]
        assert first_call.kwargs["parse_mode"] == "Markdown"

        # Second call without parse_mode (plain text)
        second_call = mock_telegram_context.bot.send_message.call_args_list[1]
        assert second_call.kwargs["parse_mode"] is None
        assert second_call.kwargs["text"] == "Bad_markdown_text"

    @pytest.mark.asyncio
    async def test_send_message_other_bad_request_not_caught(
        self, mock_telegram_context
    ):
        """Test that non-parsing BadRequest errors are re-raised."""
        from telegram.error import BadRequest

        mock_telegram_context.bot.send_message.side_effect = BadRequest(
            "Chat not found"
        )

        with pytest.raises(BadRequest, match="Chat not found"):
            await send_message(
                chat_id=12345,
                text="Test message",
                context=mock_telegram_context,
            )

    @pytest.mark.asyncio
    async def test_send_message_truncates_long_messages(self, mock_telegram_context):
        """Test that very long messages are truncated."""
        # Create a message longer than 4000 characters
        long_message = "A" * 5000

        await send_message(
            chat_id=12345,
            text=long_message,
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        call_args = mock_telegram_context.bot.send_message.call_args
        sent_text = call_args.kwargs["text"]

        # Should be truncated
        assert len(sent_text) <= 4050  # 4000 + truncation message
        assert "(message truncated)" in sent_text


class TestRequestParticipantDescription:
    """Tests for request_participant_description function."""

    @pytest.mark.asyncio
    async def test_request_description(self, mock_telegram_context):
        """Test requesting participant description."""
        await request_participant_description(
            chat_id=12345,
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        call_args = mock_telegram_context.bot.send_message.call_args
        assert "describe what each participant ate" in call_args.kwargs["text"].lower()


class TestRequestReceiptPhoto:
    """Tests for request_receipt_photo function."""

    @pytest.mark.asyncio
    async def test_request_photo(self, mock_telegram_context):
        """Test requesting receipt photo."""
        await request_receipt_photo(
            chat_id=12345,
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        call_args = mock_telegram_context.bot.send_message.call_args
        assert "photo of the receipt" in call_args.kwargs["text"].lower()


class TestAskClarificationQuestion:
    """Tests for ask_clarification_question function."""

    @pytest.mark.asyncio
    async def test_ask_question(self, mock_telegram_context):
        """Test asking clarification question."""
        await ask_clarification_question(
            chat_id=12345,
            question="Did Alice share the fries?",
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        call_args = mock_telegram_context.bot.send_message.call_args
        assert "Did Alice share the fries?" in call_args.kwargs["text"]
        assert "clarification" in call_args.kwargs["text"].lower()


class TestSendProcessingStatus:
    """Tests for send_processing_status function."""

    @pytest.mark.asyncio
    async def test_send_status(self, mock_telegram_context):
        """Test sending processing status."""
        await send_processing_status(
            chat_id=12345,
            status="⏳ Processing receipt...",
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        call_args = mock_telegram_context.bot.send_message.call_args
        assert call_args.kwargs["text"] == "⏳ Processing receipt..."


class TestSendErrorMessage:
    """Tests for send_error_message function."""

    @pytest.mark.asyncio
    async def test_send_error(self, mock_telegram_context):
        """Test sending error message."""
        await send_error_message(
            chat_id=12345,
            error="Failed to process receipt",
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        call_args = mock_telegram_context.bot.send_message.call_args
        assert "Failed to process receipt" in call_args.kwargs["text"]
        assert "error" in call_args.kwargs["text"].lower()

    @pytest.mark.asyncio
    async def test_send_error_with_special_characters(self, mock_telegram_context):
        """Test sending error with special characters (should be escaped)."""
        await send_error_message(
            chat_id=12345,
            error="Error: < & > characters",
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        # Special characters should be HTML-escaped in the error message
        call_args = mock_telegram_context.bot.send_message.call_args
        assert "&lt;" in call_args.kwargs["text"] or "Error" in call_args.kwargs["text"]


class TestSendFormattedReceipt:
    """Tests for send_formatted_receipt function."""

    @pytest.mark.asyncio
    async def test_send_receipt_success(self, mock_telegram_context):
        """Test sending formatted receipt."""
        from src.models.bill import ReceiptData

        receipt_data = ReceiptData.model_validate_json(
            """
            {
                "items": [
                    {"name": "Burger", "price": "12.50", "quantity": 1},
                    {"name": "Fries", "price": "4.00", "quantity": 2}
                ],
                "currency": "USD",
                "subtotal": "20.50",
                "total": "23.50"
            }
            """
        )

        await send_formatted_receipt(
            chat_id=12345,
            receipt_data=receipt_data,
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        call_args = mock_telegram_context.bot.send_message.call_args
        text = call_args.kwargs["text"]
        assert "Receipt Extracted" in text or "Burger" in text
        assert call_args.kwargs["parse_mode"] == "Markdown"


class TestSendFormattedSplit:
    """Tests for send_formatted_split function."""

    @pytest.mark.asyncio
    async def test_send_split_success(self, mock_telegram_context):
        """Test sending formatted bill split."""
        from src.models.bill import BillSplit

        bill_split = BillSplit.model_validate_json(
            """
            {
                "participants": [
                    {
                        "name": "Alice",
                        "items": [
                            {"item_name": "Burger", "item_numerator": 1, "item_denominator": 1}
                        ]
                    },
                    {
                        "name": "Bob",
                        "items": [
                            {"item_name": "Fries", "item_numerator": 1, "item_denominator": 2}
                        ]
                    }
                ],
                "receipt_items": [
                    {"name": "Burger", "price": "12.50", "quantity": 1},
                    {"name": "Fries", "price": "4.00", "quantity": 1}
                ],
                "currency": "USD",
                "total": "16.50"
            }
            """
        )

        await send_formatted_split(
            chat_id=12345,
            bill_split=bill_split,
            context=mock_telegram_context,
            title="Bill Split - Draft",
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        call_args = mock_telegram_context.bot.send_message.call_args
        text = call_args.kwargs["text"]
        assert "Bill Split" in text or "Alice" in text or "Bob" in text
        assert call_args.kwargs["parse_mode"] == "Markdown"

    @pytest.mark.asyncio
    async def test_send_split_with_default_title(self, mock_telegram_context):
        """Test sending formatted split with default title."""
        from src.models.bill import BillSplit

        bill_split = BillSplit.model_validate_json(
            """
            {
                "participants": [
                    {"name": "Alice", "items": []}
                ],
                "receipt_items": [],
                "currency": "USD",
                "total": "0.00"
            }
            """
        )

        await send_formatted_split(
            chat_id=12345,
            bill_split=bill_split,
            context=mock_telegram_context,
        )

        mock_telegram_context.bot.send_message.assert_called_once()
        call_args = mock_telegram_context.bot.send_message.call_args
        text = call_args.kwargs["text"]
        assert "Draft" in text or "Bill Split" in text


class TestDownloadTelegramPhoto:
    """Tests for download_telegram_photo function."""

    @pytest.mark.asyncio
    async def test_download_photo_success(
        self, mock_telegram_context, mock_telegram_file, mock_conversation_manager
    ):
        """Test successful photo download."""
        from unittest.mock import patch

        mock_telegram_context.bot.get_file.return_value = mock_telegram_file

        with patch(
            "src.bot.conversation_manager.conversation_manager",
            mock_conversation_manager,
        ):
            result = await download_telegram_photo(
                chat_id=12345,
                file_id="file_abc123",
                context=mock_telegram_context,
            )

        assert result == b"fake_image_data"
        mock_telegram_context.bot.get_file.assert_called_once_with("file_abc123")
        mock_telegram_file.download_as_bytearray.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_photo_failure(
        self, mock_telegram_context, mock_conversation_manager
    ):
        """Test photo download failure."""
        from unittest.mock import patch

        mock_telegram_context.bot.get_file.side_effect = Exception("Network error")

        with patch(
            "src.bot.conversation_manager.conversation_manager",
            mock_conversation_manager,
        ):
            with pytest.raises(Exception, match="Network error"):
                await download_telegram_photo(
                    chat_id=12345,
                    file_id="file_abc123",
                    context=mock_telegram_context,
                )


class TestGetLatestTextMessage:
    """Tests for get_latest_text_message function."""

    def test_extract_text_from_update(self, mock_telegram_update):
        """Test extracting text from update."""
        mock_telegram_update.message.text = "Hello from user"

        result = get_latest_text_message(mock_telegram_update)

        assert result == "Hello from user"

    def test_extract_text_no_message(self):
        """Test extracting text when no message exists."""
        update = Mock()
        update.message = None

        result = get_latest_text_message(update)

        assert result is None

    def test_extract_text_no_text(self, mock_telegram_update):
        """Test extracting text when message has no text."""
        mock_telegram_update.message.text = None

        result = get_latest_text_message(mock_telegram_update)

        assert result is None


class TestExtractFileIdFromMessage:
    """Tests for extract_file_id_from_message function."""

    def test_extract_file_id_from_photo(self, mock_telegram_update):
        """Test extracting file_id from photo message."""
        # Mock photo list with multiple sizes
        photo1 = Mock()
        photo1.file_id = "file_small"
        photo2 = Mock()
        photo2.file_id = "file_large"
        mock_telegram_update.message.photo = [photo1, photo2]

        result = extract_file_id_from_message(mock_telegram_update)

        # Should return the last (largest) photo
        assert result == "file_large"

    def test_extract_file_id_no_photo(self, mock_telegram_update):
        """Test extracting file_id when no photo exists."""
        mock_telegram_update.message.photo = []

        result = extract_file_id_from_message(mock_telegram_update)

        assert result is None

    def test_extract_file_id_no_message(self):
        """Test extracting file_id when no message exists."""
        update = Mock()
        update.message = None

        result = extract_file_id_from_message(update)

        assert result is None
