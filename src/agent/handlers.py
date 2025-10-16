"""Telegram handler integration for agent orchestrator.

This module provides clean integration between Telegram bot handlers
and the agent orchestrator, routing user inputs to the agent.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.agent.context_builder import AgentContext
from src.agent.orchestrator import orchestrator
from src.agent.workflow_manager import workflow_manager
from src.bot.conversation_manager import conversation_manager
from src.observability.phoenix import get_tracer
from src.tools.user_interaction import (
    extract_file_id_from_message,
    get_latest_text_message,
)

logger = logging.getLogger(__name__)

# Initialize tracer for handler-level observability
tracer = get_tracer("cheqmate.handlers")


async def handle_new_bill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /new_bill command with deterministic workflow.

    This is handled deterministically by the workflow manager:
    - Reset session
    - Request participant description
    - No agent invocation needed

    Args:
        update: Telegram update object
        context: Telegram context
    """
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    logger.info(f"Starting new bill for chat {chat_id}")

    # Create span for /new_bill handler
    with tracer.start_as_current_span(
        "handle_new_bill", openinference_span_kind="chain"
    ) as span:
        span.set_attribute("telegram.chat_id", str(chat_id))
        span.set_attribute("telegram.message_type", "command")
        span.set_attribute("telegram.command", "/new_bill")

        # Handle deterministically with workflow manager
        await workflow_manager.handle_new_bill_command(chat_id, context)


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle text messages with hybrid workflow.

    If awaiting participant description: Handled deterministically (store, try split)
    Otherwise: Delegate to agent for interpretation

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

    # Create span for text message handler
    with tracer.start_as_current_span(
        "handle_text_message", openinference_span_kind="chain"
    ) as span:
        span.set_attribute("telegram.chat_id", str(chat_id))
        span.set_attribute("telegram.message_type", "text")
        # Truncate message for span attribute
        span.set_attribute("telegram.message_preview", text[:100])

        # Check if workflow can handle deterministically
        use_agent, agent_message = await workflow_manager.should_handle_text_with_agent(
            chat_id, text, context
        )

        if not use_agent:
            # Workflow handled it completely
            logger.info(f"Text for chat {chat_id} handled deterministically")
            span.set_attribute("handler.delegated_to_agent", False)
            return

        # Need agent for interpretation
        logger.info(f"Text for chat {chat_id} delegated to agent")
        span.set_attribute("handler.delegated_to_agent", True)

        # Build agent context
        agent_context = AgentContext(
            chat_id=chat_id,
            update=update,
            context=context,
        )

        # Run agent with text message
        await orchestrator.run(agent_context=agent_context, new_message=agent_message)


async def handle_photo_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle photo messages with hybrid workflow.

    If no OCR exists: Handled deterministically (download, OCR, send receipt)
    If OCR exists: Delegate to agent (user might be correcting)

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

    # Create span for photo message handler
    with tracer.start_as_current_span(
        "handle_photo_message", openinference_span_kind="chain"
    ) as span:
        span.set_attribute("telegram.chat_id", str(chat_id))
        span.set_attribute("telegram.message_type", "photo")
        span.set_attribute("telegram.file_id", file_id)

        # Try deterministic workflow first
        handled, agent_message = await workflow_manager.handle_photo_message(
            chat_id, update, context
        )

        if handled:
            # Workflow handled it completely
            logger.info(f"Photo for chat {chat_id} handled deterministically")
            span.set_attribute("handler.delegated_to_agent", False)
            return

        # Need agent for complex scenario
        logger.info(f"Photo for chat {chat_id} delegated to agent")
        span.set_attribute("handler.delegated_to_agent", True)

        # Build agent context
        agent_context = AgentContext(
            chat_id=chat_id,
            update=update,
            context=context,
        )

        # Run agent with contextual message
        await orchestrator.run(
            agent_context=agent_context,
            new_message=agent_message,
        )
