"""User interaction tools for Telegram bot communication.

These tools handle bidirectional communication with users:
- Sending messages (requests, status updates, errors)
- Receiving data (photos, text input)
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# SENDING TOOLS (6 tools)


async def send_message(
    chat_id: int,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
    parse_mode: str = "Markdown",
) -> None:
    """
    Send a generic message to the user.

    Args:
        chat_id: Telegram chat ID
        text: Message text to send
        context: Telegram context
        parse_mode: Message formatting (default: Markdown)
    """
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    logger.debug(f"Sent message to chat {chat_id}")


async def request_participant_description(
    chat_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Ask user to describe what each participant ate.

    Args:
        chat_id: Telegram chat ID
        context: Telegram context
    """
    message = (
        "🧾 **New Bill Started!**\n\n"
        "Please describe what each participant ate.\n\n"
        "Example: *I had the burger and fries, Sarah had the salad, and John had the pasta.*"
    )
    await send_message(chat_id, message, context, parse_mode="Markdown")
    logger.info(f"Requested participant description from chat {chat_id}")


async def request_receipt_photo(
    chat_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Ask user to send a photo of the receipt.

    Args:
        chat_id: Telegram chat ID
        context: Telegram context
    """
    message = "✅ Got it!\n\nNow please send a photo of the receipt."
    await send_message(chat_id, message, context, parse_mode="Markdown")
    logger.info(f"Requested receipt photo from chat {chat_id}")


async def ask_clarification_question(
    chat_id: int, question: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Ask the user a specific clarification question.

    Args:
        chat_id: Telegram chat ID
        question: Question text to ask
        context: Telegram context
    """
    message = f"❓ **Clarification Needed**\n\n{question}"
    await send_message(chat_id, message, context, parse_mode="Markdown")
    logger.info(f"Asked clarification question to chat {chat_id}: {question}")


async def send_processing_status(
    chat_id: int, status: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Send a processing status update to the user.

    Args:
        chat_id: Telegram chat ID
        status: Status message (e.g., "⏳ Processing receipt...", "📋 Analyzing receipt...")
        context: Telegram context
    """
    await send_message(chat_id, status, context, parse_mode="Markdown")
    logger.debug(f"Sent processing status to chat {chat_id}: {status}")


async def send_error_message(
    chat_id: int, error: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Send an error message to the user.

    Args:
        chat_id: Telegram chat ID
        error: Error description
        context: Telegram context
    """
    import html

    # Escape error to avoid markdown parsing issues
    error_text = html.escape(error)
    message = (
        f"❌ **Error Processing Receipt**\n\n"
        f"Sorry, I encountered an error:\n{error_text}\n\n"
        f"Please try again with /new_bill"
    )
    # Don't use markdown to avoid parsing errors with special characters
    await context.bot.send_message(chat_id=chat_id, text=message)
    logger.error(f"Sent error message to chat {chat_id}: {error}")


# RECEIVING TOOLS (3 tools)


async def download_telegram_photo(
    file_id: str, context: ContextTypes.DEFAULT_TYPE
) -> bytes:
    """
    Download a photo from Telegram by file ID.

    Args:
        file_id: Telegram file ID
        context: Telegram context

    Returns:
        Raw image bytes
    """
    file = await context.bot.get_file(file_id)
    image_bytes = await file.download_as_bytearray()
    logger.debug(f"Downloaded photo with file_id {file_id}")
    return bytes(image_bytes)


def get_latest_text_message(update: Update) -> str | None:
    """
    Extract text message from Telegram update.

    Args:
        update: Telegram update object

    Returns:
        Text message content, or None if not available
    """
    if update.message and update.message.text:
        text = update.message.text
        logger.debug(f"Extracted text message: {text[:50]}...")
        return text
    return None


def extract_file_id_from_message(update: Update) -> str | None:
    """
    Extract photo file ID from Telegram update.

    Args:
        update: Telegram update object

    Returns:
        File ID of the largest (best quality) photo, or None if no photo
    """
    if update.message and update.message.photo:
        # Get the largest photo (best quality)
        photo = update.message.photo[-1]
        file_id = photo.file_id
        logger.debug(f"Extracted photo file_id: {file_id}")
        return file_id
    return None
