"""Telegram bot message and command handlers for receipt recognition."""

import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.conversation_manager import conversation_manager
from src.models.conversation_state import ConversationStep
from src.services.anthropic_service import AnthropicService

logger = logging.getLogger(__name__)


async def new_bill_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle the /new_bill command - start a new receipt recognition session.

    Args:
        update: Telegram update object
        context: Telegram context
    """
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    logger.info(f"Starting new bill for chat {chat_id}")

    # Get or create session and start new bill
    session = conversation_manager.get_session(chat_id)
    session.start_new_bill()

    await update.message.reply_text(
        "🧾 **New Receipt Recognition Started!**\n\n"
        "Please send a photo of the receipt.",
        parse_mode="Markdown",
    )


async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle photo messages - extract receipt items and display results.

    Args:
        update: Telegram update object
        context: Telegram context
    """
    if not update.effective_chat or not update.message or not update.message.photo:
        return

    chat_id = update.effective_chat.id
    session = conversation_manager.get_session(chat_id)

    # Only process photo if we're waiting for receipt
    if session.step != ConversationStep.AWAITING_RECEIPT:
        logger.debug(f"Ignoring photo message for chat {chat_id} (not in AWAITING_RECEIPT state)")
        return

    # Get the largest photo (best quality)
    photo = update.message.photo[-1]
    file_id = photo.file_id

    # Store receipt file ID and move to processing
    session.set_receipt(file_id)

    logger.info(f"Received receipt photo for chat {chat_id}, starting processing")

    # Send initial processing message
    processing_message = await update.message.reply_text(
        "⏳ Analyzing receipt...",
        parse_mode="Markdown",
    )

    try:
        # Download the photo
        file = await context.bot.get_file(file_id)
        image_bytes = await file.download_as_bytearray()

        # Initialize Anthropic service
        anthropic_service = AnthropicService()

        # Extract receipt
        receipt = await anthropic_service.extract_receipt_items(bytes(image_bytes))

        # Log parsed receipt data
        logger.info(f"Extracted receipt from {receipt.restaurant_name or 'Unknown'} with {len(receipt.items)} items, total: ${receipt.total:.2f}")
        for item in receipt.items:
            logger.info(f"  - {item.description}: ${item.unit_price:.2f} x{item.quantity} = ${item.line_total:.2f}")

        # Delete processing message
        await processing_message.delete()

        # Format and show receipt to user
        receipt_text_lines = ["✅ **Receipt Recognized!**\n"]

        # Add restaurant info if available
        if receipt.restaurant_name:
            receipt_text_lines.append(f"🏪 **{receipt.restaurant_name}**")
        if receipt.restaurant_address:
            receipt_text_lines.append(f"📍 {receipt.restaurant_address}")

        if receipt.restaurant_name or receipt.restaurant_address:
            receipt_text_lines.append("")  # Empty line for spacing

        # Add items
        receipt_text_lines.append("📋 **Items:**")
        for item in receipt.items:
            if item.quantity > 1:
                receipt_text_lines.append(f"• {item.description}: ${item.unit_price:.2f} x{item.quantity} = ${item.line_total:.2f}")
            else:
                receipt_text_lines.append(f"• {item.description}: ${item.line_total:.2f}")

        # Add total
        receipt_text_lines.append("")  # Empty line for spacing
        receipt_text_lines.append(f"💵 **Total: ${receipt.total:.2f}**")

        receipt_text = "\n".join(receipt_text_lines)

        # Send receipt recognition result
        await update.message.reply_text(receipt_text, parse_mode="Markdown")

        logger.info(f"Successfully processed receipt for chat {chat_id}")

        # Reset session after successful processing
        session.reset()

    except Exception as e:
        logger.error(f"Error processing receipt for chat {chat_id}: {e}", exc_info=True)

        # Try to delete processing message (may already be deleted)
        try:
            await processing_message.delete()
        except Exception:
            pass  # Message already deleted or not found

        # Escape error message to avoid markdown parsing issues
        error_text = html.escape(str(e))

        # Send error message (no markdown to avoid parsing errors)
        await update.message.reply_text(
            f"❌ Error Processing Receipt\n\n"
            f"Sorry, I encountered an error:\n{error_text}\n\n"
            f"Please try again with /new_bill"
        )

        # Reset session on error
        session.reset()
