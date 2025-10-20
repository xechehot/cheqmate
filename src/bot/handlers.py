"""Telegram bot message and command handlers for bill splitting."""

import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.conversation_manager import conversation_manager
from src.models.conversation_state import BillSession, ConversationStep
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
        "🧾 **New Bill Split Started!**\n\n"
        "Please provide:\n"
        "1️⃣ A photo of the receipt\n"
        "2️⃣ A description of who ate what\n\n"
        "You can send them in any order!\n\n"
        "Example description: *I had the burger and fries, Sarah had the salad, and John had the pasta.*",
        parse_mode="Markdown",
    )


async def process_bill_split(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: BillSession,
) -> None:
    """
    Process the bill split once both receipt and description are available.

    Args:
        update: Telegram update object
        context: Telegram context
        session: Current bill session
    """
    if not update.message:
        return

    chat_id = update.effective_chat.id if update.effective_chat else 0

    # Verify we have all required data
    if not session.is_ready_for_processing():
        logger.error(
            f"process_bill_split called but session not ready for chat {chat_id}"
        )
        return

    logger.info(f"Processing bill split for chat {chat_id}")

    # Send processing message
    processing_message = await update.message.reply_text(
        "⏳ Splitting the bill...\n\nThis may take a moment.",
        parse_mode="Markdown",
    )

    try:
        # Initialize Anthropic service
        anthropic_service = AnthropicService()

        # Split the bill
        bill_split = await anthropic_service.split_bill(
            participant_description=session.participant_description,  # type: ignore
            receipt=session.receipt_data,  # type: ignore
        )

        # Format and send the result
        result_text = bill_split.format_summary()

        # Delete processing message
        await processing_message.delete()

        # Send result
        await update.message.reply_text(result_text, parse_mode="Markdown")

        logger.info(f"Successfully processed bill split for chat {chat_id}")

        # Reset session after successful processing
        session.reset()

    except Exception as e:
        logger.error(
            f"Error processing bill split for chat {chat_id}: {e}", exc_info=True
        )

        # Try to delete processing message (may already be deleted)
        try:
            await processing_message.delete()
        except Exception:
            pass  # Message already deleted or not found

        # Escape error message to avoid markdown parsing issues
        error_text = html.escape(str(e))

        # Send error message (no markdown to avoid parsing errors)
        await update.message.reply_text(
            f"❌ Error Processing Bill Split\n\n"
            f"Sorry, I encountered an error:\n{error_text}\n\n"
            f"Please try again with /new_bill"
        )

        # Reset session on error
        session.reset()


async def photo_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle photo messages - extract receipt and check if ready to process.

    Args:
        update: Telegram update object
        context: Telegram context
    """
    if not update.effective_chat or not update.message or not update.message.photo:
        return

    chat_id = update.effective_chat.id
    session = conversation_manager.get_session(chat_id)

    # Only process photo if we're waiting for receipt
    if session.step not in (
        ConversationStep.AWAITING_BOTH,
        ConversationStep.AWAITING_RECEIPT,
    ):
        logger.debug(
            f"Ignoring photo message for chat {chat_id} (not in AWAITING state)"
        )
        return

    # Get the largest photo (best quality)
    photo = update.message.photo[-1]
    file_id = photo.file_id

    logger.info(f"Received receipt photo for chat {chat_id}, extracting receipt")

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
        logger.info(
            f"Extracted receipt from {receipt.restaurant_name or 'Unknown'} with {len(receipt.items)} items, total: ${receipt.total:.2f}"
        )
        for item in receipt.items:
            logger.info(
                f"  - {item.description}: ${item.unit_price:.2f} x{item.quantity} = ${item.line_total:.2f}"
            )

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
                receipt_text_lines.append(
                    f"• {item.description}: ${item.unit_price:.2f} x{item.quantity} = ${item.line_total:.2f}"
                )
            else:
                receipt_text_lines.append(
                    f"• {item.description}: ${item.line_total:.2f}"
                )

        # Add total
        receipt_text_lines.append("")  # Empty line for spacing
        receipt_text_lines.append(f"💵 **Total: ${receipt.total:.2f}**")

        receipt_text = "\n".join(receipt_text_lines)

        # Send receipt recognition result
        await update.message.reply_text(receipt_text, parse_mode="Markdown")

        # Store receipt in session (this updates the state based on whether description exists)
        session.set_receipt(file_id, receipt)

        # Check if we're ready to process (both receipt and description present)
        if session.is_ready_for_processing():
            # Trigger bill split processing
            await process_bill_split(update, context, session)
        else:
            # Still waiting for description
            await update.message.reply_text(
                "✅ Got it!\n\n"
                "Now please describe what each participant ate.\n\n"
                "Example: *I had the burger and fries, Sarah had the salad, and John had the pasta.*",
                parse_mode="Markdown",
            )

        logger.info(f"Successfully processed receipt for chat {chat_id}")

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


async def text_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
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

    # Only process text if we're waiting for description
    if session.step not in (
        ConversationStep.AWAITING_BOTH,
        ConversationStep.AWAITING_DESCRIPTION,
    ):
        logger.debug(
            f"Ignoring text message for chat {chat_id} (not in AWAITING state)"
        )
        return

    description = update.message.text
    logger.info(f"Received participant description for chat {chat_id}")

    # Send acknowledgment
    await update.message.reply_text(
        "✅ Got the participant description!",
        parse_mode="Markdown",
    )

    # Store description in session (this updates the state based on whether receipt exists)
    session.set_description(description)

    # Check if we're ready to process (both receipt and description present)
    if session.is_ready_for_processing():
        # Trigger bill split processing
        await process_bill_split(update, context, session)
    else:
        # Still waiting for receipt
        await update.message.reply_text(
            "Now please send a photo of the receipt.",
            parse_mode="Markdown",
        )
