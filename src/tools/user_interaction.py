"""User interaction tools for Telegram bot communication.

These tools handle bidirectional communication with users:
- Sending messages (requests, status updates, errors)
- Receiving data (photos, text input)
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# SENDING TOOLS (8 tools)


async def send_message(
    chat_id: int,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
    parse_mode: str = "Markdown",
) -> None:
    """
    Send a generic message to the user with error handling.

    This function includes:
    - Message length validation (Telegram max: 4096 chars)
    - Markdown parsing error fallback to plain text
    - Automatic truncation for very long messages

    Args:
        chat_id: Telegram chat ID
        text: Message text to send
        context: Telegram context
        parse_mode: Message formatting (default: Markdown)
    """
    from telegram.error import BadRequest

    # Telegram's message length limit
    MAX_MESSAGE_LENGTH = 4000  # Leave buffer for safety (actual limit is 4096)

    # Truncate if message is too long
    if len(text) > MAX_MESSAGE_LENGTH:
        logger.warning(
            f"Message length {len(text)} exceeds {MAX_MESSAGE_LENGTH}, truncating"
        )
        text = text[:MAX_MESSAGE_LENGTH] + "\n\n... (message truncated)"

    # Try to send with Markdown, fall back to plain text if parsing fails
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode=parse_mode
        )
        logger.debug(f"Sent message to chat {chat_id}")
    except BadRequest as e:
        # Check if this is a Markdown parsing error
        if "can't parse entities" in str(e).lower():
            logger.warning(
                f"Markdown parsing failed for chat {chat_id}, falling back to plain text. "
                f"Error: {e}"
            )
            # Retry without Markdown
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=None)
            logger.info(f"Sent message as plain text to chat {chat_id}")
        else:
            # Re-raise if it's a different kind of BadRequest
            raise


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


async def send_formatted_receipt(
    chat_id: int, receipt_data_json: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Send a formatted receipt summary to the user.

    This tool displays the OCR-extracted receipt data in a human-readable format,
    showing all items, prices, and totals. Use this after extract_receipt_ocr
    to let the user verify the recognized receipt before proceeding with splitting.

    Args:
        chat_id: Telegram chat ID
        receipt_data_json: JSON string of ReceiptData object
        context: Telegram context
    """
    from src.models.bill import ReceiptData

    try:
        # Parse JSON to ReceiptData object
        receipt_data = ReceiptData.model_validate_json(receipt_data_json)

        # Format using the model's format_summary method
        formatted_text = receipt_data.format_summary()

        # Send to user with Markdown formatting
        await send_message(chat_id, formatted_text, context, parse_mode="Markdown")

        logger.info(
            f"Sent formatted receipt to chat {chat_id}: "
            f"{len(receipt_data.items)} items, total {receipt_data.total} {receipt_data.currency}"
        )
    except Exception as e:
        logger.error(f"Failed to send formatted receipt to chat {chat_id}: {e}")
        raise ValueError(f"Failed to format and send receipt: {e}")


async def send_formatted_split(
    chat_id: int,
    bill_split_json: str,
    context: ContextTypes.DEFAULT_TYPE,
    title: str = "Bill Split - Draft",
) -> None:
    """
    Send a formatted bill split summary to the user.

    This tool displays the bill split with participant assignments and calculated totals.
    Use this to show intermediate results (draft splits) before refinement or verification,
    allowing the user to see progress and provide feedback.

    Args:
        chat_id: Telegram chat ID
        bill_split_json: JSON string of BillSplit object
        context: Telegram context
        title: Optional title for the split summary (default: "Bill Split - Draft")
    """
    from src.models.bill import BillSplit

    try:
        # Parse JSON to BillSplit object
        bill_split = BillSplit.model_validate_json(bill_split_json)

        # Format using the model's format_summary method
        formatted_text = bill_split.format_summary(title=title)

        # Send to user with Markdown formatting
        await send_message(chat_id, formatted_text, context, parse_mode="Markdown")

        logger.info(
            f"Sent formatted split to chat {chat_id}: "
            f"{len(bill_split.participants)} participants, total {bill_split.total} {bill_split.currency}"
        )
    except Exception as e:
        logger.error(f"Failed to send formatted split to chat {chat_id}: {e}")
        raise ValueError(f"Failed to format and send bill split: {e}")


# RECEIVING TOOLS (3 tools)


async def download_telegram_photo(
    chat_id: int, file_id: str, context: ContextTypes.DEFAULT_TYPE
) -> bytes:
    """
    Download a photo from Telegram by file ID and cache in session.

    Args:
        chat_id: Telegram chat ID (for session caching)
        file_id: Telegram file ID
        context: Telegram context

    Returns:
        Raw image bytes

    Raises:
        Exception: If download fails
    """
    try:
        logger.info(f"Downloading photo with file_id: {file_id}")
        file = await context.bot.get_file(file_id)
        image_bytearray = await file.download_as_bytearray()
        image_bytes = bytes(image_bytearray)
        image_size = len(image_bytes)
        logger.info(
            f"Downloaded photo: {image_size} bytes ({image_size / 1024:.1f} KB)"
        )

        # Cache image bytes in session for later use
        from src.bot.conversation_manager import conversation_manager

        session = conversation_manager.get_session(chat_id)
        session.store_image_bytes(image_bytes)

        return image_bytes
    except Exception as e:
        logger.error(f"Failed to download photo {file_id}: {e}", exc_info=True)
        raise


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
