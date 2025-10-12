"""Telegram bot message and command handlers for bill splitting workflow.

This module now uses the agentic orchestrator instead of hardcoded workflow.
All handlers delegate to the agent for flexible, intelligent processing.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

# Import agent handlers
from src.agent.handlers import (
    handle_new_bill,
    handle_photo_message,
    handle_text_message,
)

logger = logging.getLogger(__name__)


# Re-export agent handlers with original names for compatibility
async def new_bill_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /new_bill command using agent orchestrator."""
    await handle_new_bill(update, context)


async def text_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle text messages using agent orchestrator."""
    await handle_text_message(update, context)


async def photo_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle photo messages using agent orchestrator."""
    await handle_photo_message(update, context)
