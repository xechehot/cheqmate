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
        "Please describe what each participant ate.\n\n"
        "Example: *I had the burger and fries, Sarah had the salad, and John had the pasta.*",
        parse_mode="Markdown",
    )


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle text messages - capture participant descriptions.

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

    logger.info(f"Stored participant description for chat {chat_id}")

    await update.message.reply_text(
        "✅ Got it!\n\nNow please send a photo of the receipt.",
        parse_mode="Markdown",
    )


async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle photo messages - process receipt and split bill.

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

    # Send processing message
    processing_message = await update.message.reply_text(
        "⏳ Processing your receipt...\n\nThis may take a moment.",
        parse_mode="Markdown",
    )

    try:
        # Download the photo
        file = await context.bot.get_file(file_id)
        image_bytes = await file.download_as_bytearray()

        # Initialize Anthropic service
        anthropic_service = AnthropicService()

        # Step 1: Extract receipt data with currency
        await processing_message.edit_text("📋 Analyzing receipt...")
        receipt_data = await anthropic_service.extract_receipt_items(bytes(image_bytes))

        # Show receipt OCR results
        await processing_message.edit_text(receipt_data.format_summary(), parse_mode="Markdown")

        # Step 2: Split the bill
        await update.message.reply_text("🔄 Splitting bill between participants...")

        if not session.participant_description:
            raise ValueError("Missing participant description")

        bill_split = await anthropic_service.split_bill(
            participant_description=session.participant_description,
            receipt_data=receipt_data,
            image_bytes=bytes(image_bytes),
        )

        # Step 3: Verify and refine split
        verify_message = await update.message.reply_text("🔍 Verifying totals...")

        refined_split, was_refined, explanation = await anthropic_service.verify_and_refine_split(
            bill_split=bill_split,
            receipt_data=receipt_data,
        )

        # Delete verification message
        await verify_message.delete()

        # Step 4: Send final result
        if was_refined:
            title = "✅ Verified & Refined Bill Split"
            result_text = refined_split.format_summary(title=title)
            result_text += f"\n\n_Note: {explanation}_"
        else:
            title = "✅ Verified Bill Split"
            result_text = refined_split.format_summary(title=title)

        await update.message.reply_text(result_text, parse_mode="Markdown")

        logger.info(f"Successfully processed bill for chat {chat_id} (refined: {was_refined})")

        # Reset session after successful processing
        session.reset()

    except Exception as e:
        logger.error(f"Error processing bill for chat {chat_id}: {e}", exc_info=True)

        # Delete processing message
        await processing_message.delete()

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
