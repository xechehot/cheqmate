"""State management tools for accessing conversation session data.

These tools provide granular access to session state, allowing the agent to:
- Check what data exists
- Store new data
- Retrieve stored data
"""

import logging

from src.bot.conversation_manager import conversation_manager

logger = logging.getLogger(__name__)


def get_participant_description(chat_id: int) -> str | None:
    """
    Retrieve the stored participant description for a chat.

    Args:
        chat_id: Telegram chat ID

    Returns:
        Participant description text, or None if not set
    """
    session = conversation_manager.get_session(chat_id)
    description = session.participant_description
    logger.debug(
        f"Retrieved participant description for chat {chat_id}: "
        f"{'<exists>' if description else '<none>'}"
    )
    return description


def get_receipt_file_id(chat_id: int) -> str | None:
    """
    Retrieve the stored receipt file ID for a chat.

    Args:
        chat_id: Telegram chat ID

    Returns:
        Telegram file ID of the receipt photo, or None if not set
    """
    session = conversation_manager.get_session(chat_id)
    file_id = session.receipt_file_id
    logger.debug(
        f"Retrieved receipt file_id for chat {chat_id}: "
        f"{'<exists>' if file_id else '<none>'}"
    )
    return file_id


def save_participant_description(chat_id: int, description: str) -> None:
    """
    Store the participant description in the session.

    Args:
        chat_id: Telegram chat ID
        description: User's description of who ate what
    """
    session = conversation_manager.get_session(chat_id)
    session.set_description(description)
    logger.info(f"Saved participant description for chat {chat_id}")


def save_receipt_file_id(chat_id: int, file_id: str) -> None:
    """
    Store the receipt file ID in the session.

    Args:
        chat_id: Telegram chat ID
        file_id: Telegram file ID of the receipt photo
    """
    session = conversation_manager.get_session(chat_id)
    session.set_receipt(file_id)
    logger.info(f"Saved receipt file_id for chat {chat_id}")
