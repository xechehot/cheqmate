"""Telegram bot initialization and handlers."""

import logging
from typing import Final

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from src.config import settings
from src.models.state import BillState
from src.services.anthropic_service import AnthropicService
from src.services.state_service import StateService

logger = logging.getLogger(__name__)

# Bot capabilities message
CAPABILITIES_MESSAGE: Final[str] = """
👋 **Welcome to CheqMate!**

I'm your smart restaurant bill-splitting assistant. Here's what I can do:

🎤 **Voice Notes**
Send me voice notes describing who ordered what at your meal. I'll transcribe and understand who's responsible for which dishes.

📸 **Receipt Scanning**
Take a photo of your receipt, and I'll extract all the items, prices, and totals using AI-powered OCR.

🎯 **Auto-Assignment**
I'll automatically match dishes from the receipt to the people you mentioned in your voice notes using smart fuzzy matching.

💰 **Smart Splitting**
I'll calculate each person's share, including their portion of tax and tip, so everyone pays their fair amount.

📤 **Export to Apps**
Push the split directly to Splitwise or Tricount to settle up with your friends.

---

**How to use:**
1. Type /new_bill to start a fresh split
2. Send a text describing the order (e.g., "I had the burger, Sarah had the salad")
3. Send a photo of the receipt
4. Review the automatic split

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


async def new_bill_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /new_bill command."""
    if update.effective_user and update.message:
        user_id = update.effective_user.id
        state_service: StateService = context.bot_data["state_service"]
        
        state_service.clear_state(user_id)
        state_service.set_state(user_id, BillState.WAITING_FOR_DESCRIPTION)
        
        await update.message.reply_text(
            "🆕 **New Bill Started**\n\n"
            "Please tell me who ordered what.\n"
            "Example: *'I had the steak and a coke, Alice had the salad.'*",
            parse_mode="Markdown",
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages based on state."""
    if update.effective_user and update.message and update.message.text:
        user_id = update.effective_user.id
        state_service: StateService = context.bot_data["state_service"]
        user_state = state_service.get_state(user_id)
        
        if user_state.state == BillState.WAITING_FOR_DESCRIPTION:
            description = update.message.text
            state_service.update_data(user_id, description)
            state_service.set_state(user_id, BillState.WAITING_FOR_CHECK)
            
            await update.message.reply_text(
                "✅ **Description Saved**\n\n"
                "Now, please send me a clear photo of the receipt.",
                parse_mode="Markdown",
            )
        else:
            # If not in a specific state, just echo help or ignore
            pass


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages based on state."""
    if update.effective_user and update.message and update.message.photo:
        user_id = update.effective_user.id
        state_service: StateService = context.bot_data["state_service"]
        user_state = state_service.get_state(user_id)
        
        if user_state.state == BillState.WAITING_FOR_CHECK:
            # Get the largest photo
            photo_file = await update.message.photo[-1].get_file()
            image_bytes = await photo_file.download_as_bytearray()
            
            await update.message.reply_text("🔄 **Processing receipt...** This may take a moment.")
            
            anthropic_service: AnthropicService = context.bot_data["anthropic_service"]
            
            # We know description is not None because of the state flow, but type hint might complain
            description = user_state.description or ""
            
            result = anthropic_service.process_bill(bytes(image_bytes), description)
            
            await update.message.reply_text(result, parse_mode="Markdown")
            
            # Reset state after processing
            state_service.clear_state(user_id)
        else:
            pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)


def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    # Create the Application
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Initialize services and store in bot_data
    application.bot_data["state_service"] = StateService()
    application.bot_data["anthropic_service"] = AnthropicService()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new_bill", new_bill_command))
    
    # Register message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

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
    application.run_polling(allowed_updates=Update.ALL_TYPES)
