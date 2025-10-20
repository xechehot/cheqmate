"""Telegram bot initialization and handlers."""

import logging
from typing import Final

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.bot.handlers import (
    new_bill_command,
    photo_message_handler,
    text_message_handler,
)
from src.config import settings

logger = logging.getLogger(__name__)

# Bot capabilities message
CAPABILITIES_MESSAGE: Final[str] = """
👋 **Welcome to CheqMate!**

I'm your smart bill splitting assistant powered by AI.

💰 **Bill Splitting**
Split restaurant bills fairly among friends! Just send me a receipt photo and tell me who ate what, and I'll calculate each person's share.

---

**How to use:**
1. Use `/new_bill` or `/new` to start
2. Send a photo of the receipt (or describe who ate what first)
3. Describe what each person ate (or send the receipt if you haven't)
4. Get your split breakdown!

**Example:**
"I had the burger and fries, Sarah had the salad, and John had the pasta."

You can send the receipt and description in any order - I'll figure it out!

Ready to split some bills? Let's get started!

Type /help anytime to see this message again.
"""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    if update.effective_user and update.message:
        user = update.effective_user
        logger.info(f"User {user.id} ({user.username}) started the bot")
        await update.message.reply_text(
            CAPABILITIES_MESSAGE,
            parse_mode="Markdown",
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command."""
    if update.message:
        logger.info("Help command received")
        await update.message.reply_text(
            CAPABILITIES_MESSAGE,
            parse_mode="Markdown",
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(
        f"Exception while handling an update: {context.error}", exc_info=context.error
    )


def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    # Create the Application
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new_bill", new_bill_command))
    application.add_handler(CommandHandler("new", new_bill_command))

    # Register message handlers (order matters - more specific first)
    application.add_handler(MessageHandler(filters.PHOTO, photo_message_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler)
    )

    # Register error handler
    application.add_error_handler(error_handler)

    logger.info("Bot application created and handlers registered")
    return application


def run_bot() -> None:
    """Run the bot. This function will block until the bot is stopped."""
    logger.info("Starting CheqMate bot...")

    # Create the bot application
    application = create_bot()

    # Run the bot using run_polling (this blocks until stopped)
    logger.info("Bot is now running. Press Ctrl+C to stop.")
    application.run_polling()
