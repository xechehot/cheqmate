"""Telegram handler integration for agent orchestrator.

This module provides clean integration between Telegram bot handlers
and the agent orchestrator, routing user inputs to the agent.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.agent.context_builder import AgentContext
from src.agent.orchestrator import orchestrator
from src.bot.conversation_manager import conversation_manager
from src.tools.user_interaction import (
    extract_file_id_from_message,
    get_latest_text_message,
)

logger = logging.getLogger(__name__)


async def handle_new_bill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /new_bill command - start agent orchestration.

    Args:
        update: Telegram update object
        context: Telegram context
    """
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    logger.info(f"Starting new bill with agent for chat {chat_id}")

    # Reset session
    session = conversation_manager.get_session(chat_id)
    session.reset()

    # Build agent context
    agent_context = AgentContext(
        chat_id=chat_id,
        update=update,
        context=context,
    )

    # Run agent (no new message, just initiated)
    await orchestrator.run(agent_context=agent_context, new_message=None)


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle text messages - pass to agent for processing.

    Args:
        update: Telegram update object
        context: Telegram context
    """
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    text = get_latest_text_message(update)

    if not text:
        return

    logger.info(f"Received text message for chat {chat_id}: {text[:50]}...")

    # Build agent context
    agent_context = AgentContext(
        chat_id=chat_id,
        update=update,
        context=context,
    )

    # Run agent with new text
    await orchestrator.run(agent_context=agent_context, new_message=text)


async def handle_photo_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle photo messages - pass to agent for processing.

    Args:
        update: Telegram update object
        context: Telegram context
    """
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    file_id = extract_file_id_from_message(update)

    if not file_id:
        return

    logger.info(f"Received photo message for chat {chat_id}")

    # Build agent context
    agent_context = AgentContext(
        chat_id=chat_id,
        update=update,
        context=context,
    )

    # Run agent (photo info is in update, agent will extract it)
    await orchestrator.run(
        agent_context=agent_context,
        new_message=f"[User sent a photo with file_id: {file_id}]",
    )
