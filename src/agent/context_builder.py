"""Context management and prompt building for agent orchestration.

This module provides:
- AgentContext: Rich context object bundling session state and Telegram data
- System prompt: Guides agent through bill splitting workflow
- User prompt: Provides current state and new input to agent
"""

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.conversation_manager import conversation_manager
from src.models.agent_state import AgentBillSession

logger = logging.getLogger(__name__)


class AgentContext:
    """Rich context object for agent execution with state and Telegram data."""

    def __init__(
        self,
        chat_id: int,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        """
        Initialize agent context.

        Args:
            chat_id: Telegram chat ID
            update: Telegram update object
            context: Telegram context
        """
        self.chat_id = chat_id
        self.update = update
        self.telegram_context = context
        self.session: AgentBillSession = conversation_manager.get_session(chat_id)  # type: ignore

    @property
    def has_participant_description(self) -> bool:
        """Check if participant description exists in session."""
        return self.session.participant_description is not None

    @property
    def has_receipt_file_id(self) -> bool:
        """Check if receipt file ID exists in session."""
        return self.session.receipt_file_id is not None

    @property
    def has_receipt_data(self) -> bool:
        """Check if receipt OCR has been completed."""
        return self.session.has_receipt_data()

    @property
    def has_bill_split(self) -> bool:
        """Check if bill split has been created."""
        return self.session.has_bill_split()

    @property
    def has_image_bytes(self) -> bool:
        """Check if image bytes are cached."""
        return self.session.has_image_bytes()

    def get_state_summary(self) -> str:
        """
        Generate human-readable state summary for agent prompt.

        Returns:
            Formatted state summary showing what data is available
        """
        lines = ["**State:**"]

        # Participant description
        lines.append(f"Description: {'✓' if self.has_participant_description else '✗'}")

        # Receipt photo
        lines.append(f"Photo: {'✓' if self.has_receipt_file_id else '✗'}")

        # OCR results
        if self.has_receipt_data:
            receipt = self.session.receipt_data
            lines.append(f"OCR: ✓ ({len(receipt.items)} items, {receipt.total} {receipt.currency})")
        else:
            lines.append("OCR: ✗")

        # Bill split
        if self.has_bill_split:
            split = self.session.bill_split
            lines.append(f"Split: ✓ ({len(split.participants)} participants)")
        else:
            lines.append("Split: ✗")

        return "\n".join(lines)

    def to_tool_context(self) -> dict[str, Any]:
        """
        Export context data needed for tool execution.

        Returns:
            Dictionary with chat_id, update, telegram_context, and session
        """
        return {
            "chat_id": self.chat_id,
            "update": self.update,
            "telegram_context": self.telegram_context,
            "session": self.session,
        }


def build_system_prompt() -> str:
    """
    Build the system prompt for the bill splitting agent.

    This prompt defines the agent's role, capabilities, workflow, and guidelines.

    Returns:
        Complete system prompt text
    """
    return """You are a bill splitting assistant. Help users split restaurant bills fairly.

**Tools (22 total):**
User Interaction (8): send messages, request data, ask clarifications, status updates, send formatted receipt/split
State (4): get/save participant description, receipt file ID
Telegram (3): download photos, extract text/photos
LLM (3): OCR, create/refine splits
Calculations (4): totals, discrepancy, accuracy check, find unassigned items

**Workflow:**
1. **Collect**: Get participant description + receipt photo. Request missing data and STOP.
2. **Process**:
   - OCR receipt → send_formatted_receipt (verify with user)
   - Create split → send_formatted_split "Draft" (show progress)
3. **Verify (MANDATORY)**: Run ALL checks in parallel: calculate_totals, calculate_discrepancy, check_accuracy (0.02), find_unassigned_items(bill_split_json, receipt_data_json)
4. **Refine** (if needed): Use refine_split_with_llm with issue details → send_formatted_split "Refined" → re-verify (max 2 attempts)
5. **Complete**: send_message with final summary

**Rules:**
- Execute independent tools in ONE iteration (parallel execution)
- ALWAYS verify before completion - catches errors
- Ask clarification if ambiguous, never fabricate data
- Use send_processing_status for long operations
- Check state with get_* before requesting
- Save state: text → save_participant_description, photo → save_receipt_file_id

**Errors:**
- Transient (429/500/timeout): Auto-retry, continue
- Non-retryable: send_error_message, tell user /new_bill
- Never send partial results

**Done when:**
- Sent final split with send_message, OR
- Sent error with send_error_message

Target: 5-6 iterations (7-8 with refinement). Think step-by-step, use tools strategically."""


def build_user_prompt(
    agent_context: AgentContext, new_message: str | None = None
) -> str:
    """
    Build the user prompt with current state and new message.

    Args:
        agent_context: Agent context with session state
        new_message: Optional new text message or description of user action

    Returns:
        Formatted user prompt with state summary and new input
    """
    parts = [agent_context.get_state_summary()]

    if new_message:
        parts.append(f"\n**Input:** {new_message}")
    else:
        parts.append("\n**Trigger:** /new_bill")

    return "\n".join(parts)
