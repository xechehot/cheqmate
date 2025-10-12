"""Conversation state management for bill splitting workflow."""

import logging
from typing import Dict

from src.models.agent_state import AgentBillSession

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation state for multiple users with agent support."""

    def __init__(self) -> None:
        """Initialize the conversation manager with empty state."""
        self._sessions: Dict[int, AgentBillSession] = {}

    def get_session(self, chat_id: int) -> AgentBillSession:
        """
        Get or create a session for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            AgentBillSession for the chat
        """
        if chat_id not in self._sessions:
            logger.debug(f"Creating new agent session for chat {chat_id}")
            self._sessions[chat_id] = AgentBillSession()
        return self._sessions[chat_id]

    def clear_session(self, chat_id: int) -> None:
        """
        Clear the session for a chat.

        Args:
            chat_id: Telegram chat ID
        """
        if chat_id in self._sessions:
            logger.debug(f"Clearing session for chat {chat_id}")
            self._sessions[chat_id].reset()
        else:
            logger.debug(f"No session to clear for chat {chat_id}")

    def delete_session(self, chat_id: int) -> None:
        """
        Delete the session entirely for a chat.

        Args:
            chat_id: Telegram chat ID
        """
        if chat_id in self._sessions:
            logger.debug(f"Deleting session for chat {chat_id}")
            del self._sessions[chat_id]


# Global conversation manager instance
conversation_manager = ConversationManager()
