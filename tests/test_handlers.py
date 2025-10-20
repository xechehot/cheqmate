"""Tests for Telegram bot handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update

from src.bot.conversation_manager import conversation_manager
from src.bot.handlers import (
    new_bill_command,
    photo_message_handler,
    process_bill_split,
    text_message_handler,
)
from src.models.bill import Receipt
from src.models.conversation_state import ConversationStep


class TestNewBillCommand:
    """Test suite for /new_bill command handler."""

    @pytest.mark.asyncio
    async def test_new_bill_creates_session(
        self, mock_telegram_update: Update, mock_telegram_context: MagicMock
    ):
        """Test that /new_bill creates a new session."""
        chat_id = mock_telegram_update.effective_chat.id

        # Clear any existing session
        if chat_id in conversation_manager._sessions:
            del conversation_manager._sessions[chat_id]

        await new_bill_command(mock_telegram_update, mock_telegram_context)

        # Verify session was created
        session = conversation_manager.get_session(chat_id)
        assert session.step == ConversationStep.AWAITING_BOTH

    @pytest.mark.asyncio
    async def test_new_bill_sends_welcome_message(
        self, mock_telegram_update: Update, mock_telegram_context: MagicMock
    ):
        """Test that /new_bill sends welcome message."""
        await new_bill_command(mock_telegram_update, mock_telegram_context)

        # Verify reply_text was called
        mock_telegram_update.message.reply_text.assert_called_once()
        call_args = mock_telegram_update.message.reply_text.call_args
        message_text = call_args[0][0]

        assert "New Bill Split Started" in message_text
        assert "photo of the receipt" in message_text
        assert "Markdown" in str(call_args)

    @pytest.mark.asyncio
    async def test_new_bill_resets_existing_session(
        self, mock_telegram_update: Update, mock_telegram_context: MagicMock
    ):
        """Test that /new_bill resets an existing session."""
        chat_id = mock_telegram_update.effective_chat.id

        # Create existing session with data
        session = conversation_manager.get_session(chat_id)
        session.participant_description = "old data"
        session.step = ConversationStep.PROCESSING

        await new_bill_command(mock_telegram_update, mock_telegram_context)

        # Verify session was reset
        session = conversation_manager.get_session(chat_id)
        assert session.step == ConversationStep.AWAITING_BOTH
        assert session.participant_description is None


class TestPhotoMessageHandler:
    """Test suite for photo message handler."""

    @pytest.mark.asyncio
    async def test_photo_handler_extracts_receipt(
        self,
        mock_telegram_update: Update,
        mock_telegram_context: MagicMock,
        sample_receipt_usd: Receipt,
    ):
        """Test that photo handler extracts receipt data."""
        # Setup: create message with photo
        photo = MagicMock()
        photo.file_id = "test_photo_id"
        mock_telegram_update.message.photo = [photo]

        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.start_new_bill()

        # Mock AnthropicService
        with patch("src.bot.handlers.AnthropicService") as MockAnthropicService:
            mock_service = MagicMock()
            mock_service.extract_receipt_items = AsyncMock(
                return_value=sample_receipt_usd
            )
            MockAnthropicService.return_value = mock_service

            await photo_message_handler(mock_telegram_update, mock_telegram_context)

            # Verify receipt was stored
            session = conversation_manager.get_session(chat_id)
            assert session.receipt_data == sample_receipt_usd
            assert session.step == ConversationStep.AWAITING_DESCRIPTION

    @pytest.mark.asyncio
    async def test_photo_handler_displays_receipt(
        self,
        mock_telegram_update: Update,
        mock_telegram_context: MagicMock,
        sample_receipt_usd: Receipt,
    ):
        """Test that photo handler displays extracted receipt."""
        photo = MagicMock()
        photo.file_id = "test_photo_id"
        mock_telegram_update.message.photo = [photo]

        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.start_new_bill()

        with patch("src.bot.handlers.AnthropicService") as MockAnthropicService:
            mock_service = MagicMock()
            mock_service.extract_receipt_items = AsyncMock(
                return_value=sample_receipt_usd
            )
            MockAnthropicService.return_value = mock_service

            await photo_message_handler(mock_telegram_update, mock_telegram_context)

            # Verify receipt was displayed (reply_text called at least twice)
            assert mock_telegram_update.message.reply_text.call_count >= 2

            # Check that receipt info was displayed
            call_args = [
                call[0][0]
                for call in mock_telegram_update.message.reply_text.call_args_list
            ]
            full_text = " ".join(call_args)
            assert "Receipt Recognized" in full_text
            assert "Burger" in full_text
            assert "$45.00" in full_text or "45.00" in full_text

    @pytest.mark.asyncio
    async def test_photo_handler_triggers_processing_when_ready(
        self,
        mock_telegram_update: Update,
        mock_telegram_context: MagicMock,
        sample_receipt_usd: Receipt,
        sample_bill_split_usd,
    ):
        """Test that photo handler triggers processing when description exists."""
        photo = MagicMock()
        photo.file_id = "test_photo_id"
        mock_telegram_update.message.photo = [photo]

        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.start_new_bill()
        # Pre-set description
        session.participant_description = "Alice had burger, Bob had salad"

        with patch("src.bot.handlers.AnthropicService") as MockAnthropicService:
            mock_service = MagicMock()
            mock_service.extract_receipt_items = AsyncMock(
                return_value=sample_receipt_usd
            )
            mock_service.split_bill = AsyncMock(return_value=sample_bill_split_usd)
            MockAnthropicService.return_value = mock_service

            await photo_message_handler(mock_telegram_update, mock_telegram_context)

            # Verify split_bill was called
            mock_service.split_bill.assert_called_once()

    @pytest.mark.asyncio
    async def test_photo_handler_ignores_when_not_awaiting(
        self, mock_telegram_update: Update, mock_telegram_context: MagicMock
    ):
        """Test that photo handler ignores photos when not in awaiting state."""
        photo = MagicMock()
        photo.file_id = "test_photo_id"
        mock_telegram_update.message.photo = [photo]

        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.step = ConversationStep.IDLE  # Not awaiting anything

        # Reset reply_text mock
        mock_telegram_update.message.reply_text.reset_mock()

        await photo_message_handler(mock_telegram_update, mock_telegram_context)

        # Verify no response was sent
        mock_telegram_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_photo_handler_error_handling(
        self, mock_telegram_update: Update, mock_telegram_context: MagicMock
    ):
        """Test photo handler error handling."""
        photo = MagicMock()
        photo.file_id = "test_photo_id"
        mock_telegram_update.message.photo = [photo]

        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.start_new_bill()

        # Mock service to raise error
        with patch("src.bot.handlers.AnthropicService") as MockAnthropicService:
            mock_service = MagicMock()
            mock_service.extract_receipt_items = AsyncMock(
                side_effect=Exception("API Error")
            )
            MockAnthropicService.return_value = mock_service

            await photo_message_handler(mock_telegram_update, mock_telegram_context)

            # Verify error message was sent
            call_args = [
                call[0][0]
                for call in mock_telegram_update.message.reply_text.call_args_list
            ]
            error_text = " ".join(call_args)
            assert "Error" in error_text or "error" in error_text

            # Verify session was reset
            session = conversation_manager.get_session(chat_id)
            assert session.step == ConversationStep.IDLE


class TestTextMessageHandler:
    """Test suite for text message handler."""

    @pytest.mark.asyncio
    async def test_text_handler_stores_description(
        self, mock_telegram_update: Update, mock_telegram_context: MagicMock
    ):
        """Test that text handler stores participant description."""
        mock_telegram_update.message.text = "Alice had burger, Bob had salad"

        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.start_new_bill()

        await text_message_handler(mock_telegram_update, mock_telegram_context)

        # Verify description was stored
        session = conversation_manager.get_session(chat_id)
        assert session.participant_description == "Alice had burger, Bob had salad"
        assert session.step == ConversationStep.AWAITING_RECEIPT

    @pytest.mark.asyncio
    async def test_text_handler_triggers_processing_when_ready(
        self,
        mock_telegram_update: Update,
        mock_telegram_context: MagicMock,
        sample_receipt_usd: Receipt,
        sample_bill_split_usd,
    ):
        """Test that text handler triggers processing when receipt exists."""
        mock_telegram_update.message.text = "Alice had burger, Bob had salad"

        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.start_new_bill()
        # Pre-set receipt
        session.receipt_file_id = "test_file"
        session.receipt_data = sample_receipt_usd
        session.step = ConversationStep.AWAITING_DESCRIPTION

        with patch("src.bot.handlers.AnthropicService") as MockAnthropicService:
            mock_service = MagicMock()
            mock_service.split_bill = AsyncMock(return_value=sample_bill_split_usd)
            MockAnthropicService.return_value = mock_service

            await text_message_handler(mock_telegram_update, mock_telegram_context)

            # Verify split_bill was called
            mock_service.split_bill.assert_called_once()

    @pytest.mark.asyncio
    async def test_text_handler_ignores_when_not_awaiting(
        self, mock_telegram_update: Update, mock_telegram_context: MagicMock
    ):
        """Test that text handler ignores text when not in awaiting state."""
        mock_telegram_update.message.text = "Some random text"

        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.step = ConversationStep.IDLE

        # Reset reply_text mock
        mock_telegram_update.message.reply_text.reset_mock()

        await text_message_handler(mock_telegram_update, mock_telegram_context)

        # Verify no response was sent
        mock_telegram_update.message.reply_text.assert_not_called()


class TestProcessBillSplit:
    """Test suite for bill split processing."""

    @pytest.mark.asyncio
    async def test_process_bill_split_success(
        self,
        mock_telegram_update: Update,
        mock_telegram_context: MagicMock,
        sample_receipt_usd: Receipt,
        sample_bill_split_usd,
    ):
        """Test successful bill split processing."""
        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.receipt_data = sample_receipt_usd
        session.participant_description = "Alice had burger, Bob had salad"
        session.step = ConversationStep.PROCESSING

        with patch("src.bot.handlers.AnthropicService") as MockAnthropicService:
            mock_service = MagicMock()
            mock_service.split_bill = AsyncMock(return_value=sample_bill_split_usd)
            MockAnthropicService.return_value = mock_service

            await process_bill_split(
                mock_telegram_update, mock_telegram_context, session
            )

            # Verify split result was sent
            call_args = [
                call[0][0]
                for call in mock_telegram_update.message.reply_text.call_args_list
            ]
            result_text = " ".join(call_args)
            assert "Bill Split Summary" in result_text
            assert "Alice" in result_text
            assert "Bob" in result_text

    @pytest.mark.asyncio
    async def test_process_bill_split_includes_validation(
        self,
        mock_telegram_update: Update,
        mock_telegram_context: MagicMock,
        sample_receipt_usd: Receipt,
        sample_bill_split_usd,
    ):
        """Test that bill split includes validation message."""
        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.receipt_data = sample_receipt_usd
        session.participant_description = "Alice had burger, Bob had salad"
        session.step = ConversationStep.PROCESSING

        with patch("src.bot.handlers.AnthropicService") as MockAnthropicService:
            mock_service = MagicMock()
            mock_service.split_bill = AsyncMock(return_value=sample_bill_split_usd)
            MockAnthropicService.return_value = mock_service

            await process_bill_split(
                mock_telegram_update, mock_telegram_context, session
            )

            # Verify validation message was included
            call_args = [
                call[0][0]
                for call in mock_telegram_update.message.reply_text.call_args_list
            ]
            result_text = " ".join(call_args)
            # Should have validation emoji (✅ or ⚠️)
            assert "✅" in result_text or "⚠️" in result_text

    @pytest.mark.asyncio
    async def test_process_bill_split_resets_session(
        self,
        mock_telegram_update: Update,
        mock_telegram_context: MagicMock,
        sample_receipt_usd: Receipt,
        sample_bill_split_usd,
    ):
        """Test that successful processing resets the session."""
        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.receipt_data = sample_receipt_usd
        session.participant_description = "Alice had burger"
        session.step = ConversationStep.PROCESSING

        with patch("src.bot.handlers.AnthropicService") as MockAnthropicService:
            mock_service = MagicMock()
            mock_service.split_bill = AsyncMock(return_value=sample_bill_split_usd)
            MockAnthropicService.return_value = mock_service

            await process_bill_split(
                mock_telegram_update, mock_telegram_context, session
            )

            # Verify session was reset
            session = conversation_manager.get_session(chat_id)
            assert session.step == ConversationStep.IDLE
            assert session.receipt_data is None
            assert session.participant_description is None

    @pytest.mark.asyncio
    async def test_process_bill_split_error_handling(
        self,
        mock_telegram_update: Update,
        mock_telegram_context: MagicMock,
        sample_receipt_usd: Receipt,
    ):
        """Test error handling in bill split processing."""
        chat_id = mock_telegram_update.effective_chat.id
        session = conversation_manager.get_session(chat_id)
        session.receipt_data = sample_receipt_usd
        session.participant_description = "Alice had burger"
        session.step = ConversationStep.PROCESSING

        with patch("src.bot.handlers.AnthropicService") as MockAnthropicService:
            mock_service = MagicMock()
            mock_service.split_bill = AsyncMock(side_effect=Exception("Split error"))
            MockAnthropicService.return_value = mock_service

            await process_bill_split(
                mock_telegram_update, mock_telegram_context, session
            )

            # Verify error message was sent
            call_args = [
                call[0][0]
                for call in mock_telegram_update.message.reply_text.call_args_list
            ]
            error_text = " ".join(call_args)
            assert "Error" in error_text or "error" in error_text

            # Verify session was reset even on error
            session = conversation_manager.get_session(chat_id)
            assert session.step == ConversationStep.IDLE
