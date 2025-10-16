"""Telegram bot message and command handlers for bill splitting workflow."""

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
    Handle the /new_bill command - start a new bill splitting session.

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
        "🧾 **New Bill Started!**\n\n"
        "Please send a photo of the receipt.",
        parse_mode="Markdown",
    )


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle text messages - capture participant descriptions and process bill.

    Args:
        update: Telegram update object
        context: Telegram context
    """
    if not update.effective_chat or not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    session = conversation_manager.get_session(chat_id)

    # Only process text if we're waiting for participant description
    if session.step != ConversationStep.AWAITING_DESCRIPTION:
        logger.debug(f"Ignoring text message for chat {chat_id} (not in AWAITING_DESCRIPTION state)")
        return

    # Store the description
    description = update.message.text
    session.set_description(description)

    logger.info(f"Stored participant description for chat {chat_id}, starting processing")

    # Send initial processing message
    processing_message = await update.message.reply_text(
        "⏳ Analyzing receipt...",
        parse_mode="Markdown",
    )

    try:
        # Download the photo
        if not session.receipt_file_id:
            raise ValueError("Missing receipt file ID")

        file = await context.bot.get_file(session.receipt_file_id)
        image_bytes = await file.download_as_bytearray()

        # Initialize Anthropic service
        anthropic_service = AnthropicService()

        # Extract receipt items
        receipt_items = await anthropic_service.extract_receipt_items(bytes(image_bytes))

        # Log parsed receipt data
        logger.info(f"Extracted {len(receipt_items)} items from receipt for chat {chat_id}")
        for item in receipt_items:
            logger.info(f"  - {item.description}: ${item.unit_price:.2f} x{item.quantity} = ${item.line_total:.2f}")

        # Delete processing message
        await processing_message.delete()

        # Format and show receipt items to user
        receipt_text_lines = ["✅ **Receipt Recognized!**\n", "**Items Found:**"]
        for item in receipt_items:
            if item.quantity > 1:
                receipt_text_lines.append(f"• {item.description}: ${item.unit_price:.2f} x{item.quantity} = ${item.line_total:.2f}")
            else:
                receipt_text_lines.append(f"• {item.description}: ${item.line_total:.2f}")

        receipt_text_lines.append("\n⏳ Matching items to participants...")
        receipt_text = "\n".join(receipt_text_lines)

        # Send receipt recognition result
        await update.message.reply_text(receipt_text, parse_mode="Markdown")

        # Split the bill
        if not session.participant_description:
            raise ValueError("Missing participant description")

        bill_split = await anthropic_service.split_bill(
            participant_description=session.participant_description,
            receipt_items=receipt_items,
            image_bytes=bytes(image_bytes),
        )

        # Format and send the result
        result_text = bill_split.format_summary()

        # Send result
        await update.message.reply_text(result_text, parse_mode="Markdown")

        logger.info(f"Successfully processed bill for chat {chat_id}")

        # Reset session after successful processing
        session.reset()

    except Exception as e:
        logger.error(f"Error processing bill for chat {chat_id}: {e}", exc_info=True)

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


async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle photo messages - store receipt and ask for description.

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

    # Store receipt file ID and move to next step
    session.set_receipt(file_id)

    logger.info(f"Stored receipt photo for chat {chat_id}")

    await update.message.reply_text(
        "✅ Got it!\n\n"
        "Now please describe what each participant ate.\n\n"
        "Example: *I had the burger and fries, Sarah had the salad, and John had the pasta.*",
        parse_mode="Markdown",
    )
