"""State management tools for accessing conversation session data.

These tools provide granular access to session state, allowing the agent to:
- Check what data exists
- Store new data
- Retrieve stored data
"""

import logging

from src.bot.conversation_manager import conversation_manager
from src.tools.llm_processing import merge_participant_descriptions

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


async def update_participant_description(chat_id: int, description: str) -> None:
    """
    Update participant description, intelligently merging with existing if present.

    This tool encapsulates the merge logic:
    - If no existing description: Sets the description directly
    - If existing description exists: Uses LLM to intelligently merge
      (handles corrections, additions, clarifications)

    Args:
        chat_id: Telegram chat ID
        description: User's new/updated description of who ate what

    Raises:
        ValueError: If merge operation fails (when existing description exists)
    """
    session = conversation_manager.get_session(chat_id)
    existing = session.participant_description

    if existing:
        # Merge intelligently with LLM
        logger.info(
            f"Chat {chat_id}: Merging new description with existing "
            f"({len(existing)} chars + {len(description)} chars)"
        )
        merged = await merge_participant_descriptions(chat_id, existing, description)
        session.set_description(merged)
        logger.info(
            f"Chat {chat_id}: Successfully merged participant description "
            f"(result: {len(merged)} chars)"
        )
    else:
        # First time - just set
        session.set_description(description)
        logger.info(f"Chat {chat_id}: Set initial participant description")


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
