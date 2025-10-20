"""Tests for bot initialization and command handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import Application

from src.bot.bot import (
    CAPABILITIES_MESSAGE,
    create_bot,
    error_handler,
    help_command,
    start_command,
)


class TestCreateBot:
    """Test suite for bot creation and configuration."""

    @patch("src.bot.bot.settings")
    def test_create_bot_returns_application(self, mock_settings):
        """Test that create_bot returns a configured Application."""
        mock_settings.telegram_bot_token = "test_token"

        app = create_bot()

        assert isinstance(app, Application)
        assert app.bot.token == "test_token"

    @patch("src.bot.bot.settings")
    def test_create_bot_registers_command_handlers(self, mock_settings):
        """Test that all command handlers are registered."""
        mock_settings.telegram_bot_token = "test_token"

        app = create_bot()

        # Get all handlers
        handlers = app.handlers[0]  # Default handler group

        # Verify we have multiple handlers registered
        assert len(handlers) > 0

        # Check that command handlers exist
        handler_types = [type(h).__name__ for h in handlers]
        assert "CommandHandler" in handler_types
        assert "MessageHandler" in handler_types

    @patch("src.bot.bot.settings")
    def test_create_bot_registers_error_handler(self, mock_settings):
        """Test that error handler is registered."""
        mock_settings.telegram_bot_token = "test_token"

        app = create_bot()

        # Verify error handler was added
        assert len(app.error_handlers) > 0


class TestStartCommand:
    """Test suite for /start command."""

    @pytest.mark.asyncio
    async def test_start_command_sends_welcome_message(
        self, mock_telegram_update: Update, mock_telegram_context: MagicMock
    ):
        """Test that /start sends the capabilities message."""
        await start_command(mock_telegram_update, mock_telegram_context)

        # Verify reply_text was called
        mock_telegram_update.message.reply_text.assert_called_once()

        # Verify the message content
        call_args = mock_telegram_update.message.reply_text.call_args
        message_text = call_args[0][0]
        assert message_text == CAPABILITIES_MESSAGE

        # Verify Markdown parsing
        assert call_args.kwargs["parse_mode"] == "Markdown"

    @pytest.mark.asyncio
    async def test_start_command_includes_key_information(
        self, mock_telegram_update: Update, mock_telegram_context: MagicMock
    ):
        """Test that /start message includes key information."""
        await start_command(mock_telegram_update, mock_telegram_context)

        call_args = mock_telegram_update.message.reply_text.call_args
        message_text = call_args[0][0]

        # Verify key content is present
        assert "CheqMate" in message_text
        assert "bill splitting" in message_text.lower()
        assert "/new_bill" in message_text
        assert "/help" in message_text

    @pytest.mark.asyncio
    async def test_start_command_without_message(self, mock_telegram_context: MagicMock):
        """Test start command handles missing message gracefully."""
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.message = None

        # Should not raise an error
        await start_command(update, mock_telegram_context)

    @pytest.mark.asyncio
    async def test_start_command_without_user(
        self, mock_telegram_context: MagicMock
    ):
        """Test start command handles missing user gracefully."""
        update = MagicMock(spec=Update)
        update.effective_user = None
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        # Should not raise an error
        await start_command(update, mock_telegram_context)


class TestHelpCommand:
    """Test suite for /help command."""

    @pytest.mark.asyncio
    async def test_help_command_sends_capabilities_message(
        self, mock_telegram_update: Update, mock_telegram_context: MagicMock
    ):
        """Test that /help sends the capabilities message."""
        await help_command(mock_telegram_update, mock_telegram_context)

        # Verify reply_text was called
        mock_telegram_update.message.reply_text.assert_called_once()

        # Verify the message content
        call_args = mock_telegram_update.message.reply_text.call_args
        message_text = call_args[0][0]
        assert message_text == CAPABILITIES_MESSAGE

        # Verify Markdown parsing
        assert call_args.kwargs["parse_mode"] == "Markdown"

    @pytest.mark.asyncio
    async def test_help_command_without_message(self, mock_telegram_context: MagicMock):
        """Test help command handles missing message gracefully."""
        update = MagicMock(spec=Update)
        update.message = None

        # Should not raise an error
        await help_command(update, mock_telegram_context)


class TestErrorHandler:
    """Test suite for error handler."""

    @pytest.mark.asyncio
    async def test_error_handler_logs_error(self):
        """Test that error handler logs errors."""
        update = MagicMock(spec=Update)
        context = MagicMock()
        context.error = Exception("Test error")

        with patch("src.bot.bot.logger") as mock_logger:
            await error_handler(update, context)

            # Verify error was logged
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert "Exception while handling an update" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_error_handler_handles_none_update(self):
        """Test error handler with None update."""
        context = MagicMock()
        context.error = Exception("Test error")

        with patch("src.bot.bot.logger") as mock_logger:
            # Should not raise an error
            await error_handler(None, context)

            # Verify error was still logged
            mock_logger.error.assert_called_once()


class TestCapabilitiesMessage:
    """Test suite for capabilities message content."""

    def test_capabilities_message_has_welcome(self):
        """Test that capabilities message has welcome text."""
        assert "Welcome" in CAPABILITIES_MESSAGE
        assert "CheqMate" in CAPABILITIES_MESSAGE

    def test_capabilities_message_has_commands(self):
        """Test that capabilities message lists available commands."""
        assert "/new_bill" in CAPABILITIES_MESSAGE or "/new" in CAPABILITIES_MESSAGE
        assert "/help" in CAPABILITIES_MESSAGE

    def test_capabilities_message_has_instructions(self):
        """Test that capabilities message has usage instructions."""
        assert "photo" in CAPABILITIES_MESSAGE.lower()
        assert "receipt" in CAPABILITIES_MESSAGE.lower()

    def test_capabilities_message_has_example(self):
        """Test that capabilities message has an example."""
        # Check for example-like content
        message_lower = CAPABILITIES_MESSAGE.lower()
        assert "example" in message_lower or "burger" in message_lower
