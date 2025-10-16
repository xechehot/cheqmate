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

    @property
    def has_split_quality(self) -> bool:
        """Check if split quality metrics have been calculated."""
        return self.session.has_split_quality_metrics()

    @property
    def has_refined_split(self) -> bool:
        """Check if split has been refined at least once."""
        return self.session.has_refined_split()

    def get_state_summary(self) -> str:
        """
        Generate human-readable state summary for agent prompt.

        Returns:
            Formatted state summary showing what data is available
        """
        lines = ["**State:**"]

        # Participant description
        lines.append(f"Description: {'[+]' if self.has_participant_description else '[-]'}")

        # Receipt photo
        lines.append(f"Photo: {'[+]' if self.has_receipt_file_id else '[-]'}")

        # OCR results
        if self.has_receipt_data:
            receipt = self.session.receipt_data
            lines.append(f"OCR: [+] ({len(receipt.items)} items, {receipt.total} {receipt.currency})")
        else:
            lines.append("OCR: [-]")

        # Bill split
        if self.has_bill_split:
            split = self.session.bill_split
            receipt = self.session.receipt_data
            # Show participant count and total amount with currency
            lines.append(f"Split: [+] ({len(split.participants)} participants, {receipt.total} {receipt.currency})")
        else:
            lines.append("Split: [-]")

        # Split quality
        if self.has_split_quality:
            metrics = self.session.split_quality_metrics
            lines.append(
                f"Split quality: [+] (discrepancy: {metrics.total_discrepancy}, "
                f"unassigned: {metrics.unassigned_count})"
            )
        else:
            lines.append("Split quality: [-]")

        # Split refined
        if self.has_refined_split:
            count = self.session.split_refinement_count
            refinement_text = "refinement" if count == 1 else "refinements"
            lines.append(f"Split refined: [+] ({count} {refinement_text})")
        else:
            lines.append("Split refined: [-]")

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

    This prompt defines the agent's role, capabilities, workflow, and guidelines
    for the hybrid deterministic+agentic approach.

    Returns:
        Complete system prompt text
    """
    return """You are a bill splitting assistant. Help users split restaurant bills fairly.

**IMPORTANT - Workflow Manager:**
Many tasks are now AUTOMATED before you are invoked:
- /new_bill → Auto-handled (description already requested)
- Photo received → Auto-processed (OCR done, receipt sent to user)
- Draft split created → Auto-created (if description exists)
- You are invoked ONLY when agent decision-making is needed

**Tools (11 total - reduced from 22):**
User Interaction (5): send messages, clarifications, formatted receipt/split, errors
LLM Processing (3): create split, refine split, evaluate quality
Quality (1): evaluate_split_quality (consolidated - replaces 4 calculation tools)
State Management (1): save_participant_description (when description is awaited)

**Your Workflow:**
1. **Check State**: OCR and photo handling already done. Check session for:
   - participant_description (from user text)
   - receipt_data (from automated OCR)

2. **Create Split**:
   - Use create_initial_bill_split (takes NO parameters - auto-fetches both receipt_data and description from session)
   - Show with send_formatted_split "Draft"

3. **Verify (MANDATORY - ONE CALL)**:
   - Use evaluate_split_quality (returns ALL metrics)
   - Check: is_complete, passes_accuracy_threshold, unassigned_items, total_discrepancy

4. **Evaluate (OPTIONAL)**:
   - Use evaluate_bill_quality_with_llm for qualitative assessment
   - Provides confidence, issues, recommendations

5. **Refine** (if needed):
   - Use refine_split_with_llm with detailed issue_explanation
   - Re-verify with evaluate_split_quality
   - Max 2 refinement attempts

6. **Complete**:
   - send_message with final summary (participant totals, payment instructions)

**Rules:**
- Execute independent tools in parallel when possible
- Use save_participant_description only if user provides description in non-standard way
- Ask clarification if user input is ambiguous
- NEVER fabricate data or skip verification

**Errors:**
- Transient (429/500): Auto-retry, continue
- Non-retryable: send_error_message with /new_bill suggestion

**Done when:**
- Sent final split summary with send_message, OR
- Sent error with send_error_message

**Target: 3-4 iterations (5-6 with refinement) - much faster than before!**

Think step-by-step. Be efficient."""


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
