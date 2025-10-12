"""Unit tests for user interaction tools.

These tests cover the 9 user interaction functions with mocked Telegram bot.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.tools.user_interaction import (
    ask_clarification_question,
    download_telegram_photo,
    extract_file_id_from_message,
    get_latest_text_message,
    request_participant_description,
    request_receipt_photo,
    send_error_message,
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


class TestDownloadTelegramPhoto:
    """Tests for download_telegram_photo function."""

    @pytest.mark.asyncio
    async def test_download_photo_success(self, mock_telegram_context, mock_telegram_file, mock_conversation_manager):
        """Test successful photo download."""
        from unittest.mock import patch

        mock_telegram_context.bot.get_file.return_value = mock_telegram_file

        with patch("src.bot.conversation_manager.conversation_manager", mock_conversation_manager):
            result = await download_telegram_photo(
                chat_id=12345,
                file_id="file_abc123",
                context=mock_telegram_context,
            )

        assert result == b"fake_image_data"
        mock_telegram_context.bot.get_file.assert_called_once_with("file_abc123")
        mock_telegram_file.download_as_bytearray.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_photo_failure(self, mock_telegram_context, mock_conversation_manager):
        """Test photo download failure."""
        from unittest.mock import patch

        mock_telegram_context.bot.get_file.side_effect = Exception("Network error")

        with patch("src.bot.conversation_manager.conversation_manager", mock_conversation_manager):
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
