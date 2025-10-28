"""Telegram bot message and command handlers for bill splitting."""

import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.conversation_manager import conversation_manager
from src.models.bill import format_currency
from src.models.conversation_state import BillSession, ConversationStep
from src.services.anthropic_service import AnthropicService
from src.utils.bill_calculations import analyze_split_discrepancy, validate_split

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

        # Step 1: Get initial split
        initial_split = await anthropic_service.split_bill(
            participant_description=session.participant_description,  # type: ignore
            receipt=session.receipt_data,  # type: ignore
        )

        # Step 2: Validate initial split and analyze discrepancy
        initial_is_valid, initial_validation_message, initial_details = validate_split(
            initial_split
        )
        initial_discrepancy = analyze_split_discrepancy(initial_split)

        # Step 3: Display initial split
        initial_result_text = "📊 **Initial Split:**\n\n"
        initial_result_text += initial_split.format_summary()
        initial_result_text += f"\n\n{initial_validation_message}"

        # Delete processing message
        await processing_message.delete()

        # Send initial split
        await update.message.reply_text(initial_result_text, parse_mode="Markdown")

        # Step 4: Refine the split with LLM
        refining_message = await update.message.reply_text(
            "⏳ Refining the split with AI...\n\nAnalyzing discrepancies and improving assignments.",
            parse_mode="Markdown",
        )

        refined_split = await anthropic_service.refine_bill_split(
            receipt=session.receipt_data,  # type: ignore
            initial_split=initial_split,
            discrepancy=initial_discrepancy,
        )

        # Step 5: Validate refined split and analyze its discrepancy
        refined_is_valid, refined_validation_message, refined_details = validate_split(
            refined_split
        )
        refined_discrepancy = analyze_split_discrepancy(refined_split)

        # Step 6: Display refined split with improvement metrics
        refined_result_text = "✨ **Refined Split:**\n\n"
        refined_result_text += refined_split.format_summary()
        refined_result_text += f"\n\n{refined_validation_message}"

        # Add improvement summary
        initial_pct = initial_details["discrepancy_pct"]
        refined_pct = refined_details["discrepancy_pct"]
        improvement_text = "\n\n📈 **Improvement:**\n"
        improvement_text += f"• Discrepancy: {initial_pct:.2f}% → {refined_pct:.2f}%\n"
        if len(initial_discrepancy.missed_items) > 0:
            improvement_text += f"• Missed items: {len(initial_discrepancy.missed_items)} → {len(refined_discrepancy.missed_items)}"

        refined_result_text += improvement_text

        # Delete refining message
        await refining_message.delete()

        # Send refined split
        await update.message.reply_text(refined_result_text, parse_mode="Markdown")

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
        total_fmt = format_currency(receipt.total, receipt.currency)
        logger.info(
            f"Extracted receipt from {receipt.restaurant_name or 'Unknown'} with {len(receipt.items)} items, total: {total_fmt}"
        )
        for item in receipt.items:
            unit_price_fmt = format_currency(item.unit_price, receipt.currency)
            line_total_fmt = format_currency(item.line_total, receipt.currency)
            logger.info(
                f"  - {item.description}: {unit_price_fmt} x{item.quantity} = {line_total_fmt}"
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
                unit_price_fmt = format_currency(item.unit_price, receipt.currency)
                line_total_fmt = format_currency(item.line_total, receipt.currency)
                receipt_text_lines.append(
                    f"• {item.description}: {unit_price_fmt} x{item.quantity} = {line_total_fmt}"
                )
            else:
                line_total_fmt = format_currency(item.line_total, receipt.currency)
                receipt_text_lines.append(f"• {item.description}: {line_total_fmt}")

        # Add total
        receipt_text_lines.append("")  # Empty line for spacing
        total_fmt = format_currency(receipt.total, receipt.currency)
        receipt_text_lines.append(f"💵 **Total: {total_fmt}**")

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
