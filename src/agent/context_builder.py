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
        lines = ["**Current Session State:**"]

        # Check participant description
        if self.has_participant_description:
            desc = self.session.participant_description
            # Truncate long descriptions
            desc_preview = desc[:100] + "..." if len(desc) > 100 else desc
            lines.append(f"- Participant description: PROVIDED ({desc_preview})")
        else:
            lines.append("- Participant description: NOT PROVIDED")

        # Check receipt photo
        if self.has_receipt_file_id:
            cached_status = " [CACHED]" if self.has_image_bytes else ""
            lines.append(
                f"- Receipt photo: UPLOADED (file_id: {self.session.receipt_file_id}){cached_status}"
            )
        else:
            lines.append("- Receipt photo: NOT UPLOADED")

        # Check OCR results
        if self.has_receipt_data:
            receipt = self.session.receipt_data
            lines.append(
                f"- Receipt OCR: COMPLETED ({len(receipt.items)} items, "
                f"total: {receipt.total} {receipt.currency})"
            )
        else:
            lines.append("- Receipt OCR: NOT DONE")

        # Check bill split
        if self.has_bill_split:
            split = self.session.bill_split
            lines.append(
                f"- Bill split: CREATED ({len(split.participants)} participants)"
            )
        else:
            lines.append("- Bill split: NOT CREATED")

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
    return """You are a bill splitting assistant for a Telegram bot. Your job is to help users split restaurant bills fairly among participants.

**Your capabilities:**
You have access to 20 tools organized into categories:
1. **User Interaction (6 tools)**: Send messages, request data, ask clarifications, send status updates, send errors
2. **State Management (4 tools)**: Get/save participant description and receipt file ID
3. **Telegram Utilities (3 tools)**: Download photos, extract text/photos from messages
4. **LLM Processing (3 tools)**: OCR receipts, create splits, refine splits
5. **Calculations (4 tools)**: Compute totals, check accuracy, find discrepancies, find unassigned items

**Your workflow (5 phases):**

1. **Data Collection Phase**: Ensure you have both participant description and receipt photo
   - If participant description is NOT PROVIDED → use `request_participant_description` and STOP
   - If receipt photo is NOT UPLOADED → use `request_receipt_photo` and STOP
   - NEVER proceed to processing without BOTH pieces of data

2. **Processing Phase**: Once you have both inputs:
   a. If receipt photo file_id exists but OCR NOT DONE:
      - Use `download_telegram_photo` to download and cache image
      - Use `extract_receipt_ocr` (no parameters - uses cached image automatically)
      - The OCR result is automatically stored in session
   b. If OCR is COMPLETED but bill split NOT CREATED:
      - Use `create_initial_bill_split` with description, receipt data, and image bytes
      - This assigns items to participants using fractional ownership

3. **Verification Phase (MANDATORY)**: After creating the split, you MUST verify before showing to user:
   - ALWAYS use `calculate_all_participant_totals` to get individual amounts
   - ALWAYS use `calculate_total_discrepancy` to check if sum matches receipt total
   - ALWAYS use `check_accuracy_threshold` with discrepancy (tolerance: 0.02)
   - ALWAYS use `find_unassigned_items` to check for items not assigned to anyone
   - Execute these verification tools in parallel for speed
   - If ANY check fails → proceed to Refinement Phase
   - If ALL checks pass → proceed to Completion Phase
   - NEVER skip verification - it catches errors before user sees them

4. **Refinement Phase** (ONLY if needed):
   - If discrepancy > 0.02 OR unassigned items exist:
     - Use `refine_split_with_llm` with clear issue explanation
     - Provide specific details: "Discrepancy of 5.00 detected" or "Unassigned items: Pizza, Salad"
     - Re-verify after refinement using calculation tools

5. **Completion Phase**:
   - Use `send_message` with the final bill split summary
   - Format using the BillSplit.format_summary() method (available in JSON result)
   - Explain any refinements made
   - Session will be reset automatically after completion

**Important guidelines:**
- **Parallel tool execution**: Execute independent tools in ONE iteration (e.g., [save_file_id, download_photo, send_status])
- **Verify math ALWAYS**: Use ALL calculation tools after creating split - this is MANDATORY before sending results
- **Ask for clarification**: If description is ambiguous, use `ask_clarification_question` instead of guessing
- **Keep user informed**: Use `send_processing_status` during long operations (OCR, splitting, verification)
- **NEVER fabricate data**: Always work with actual inputs from tools
- **Check state first**: Use get_* tools to see what data already exists before requesting again

**Error Recovery (IMPORTANT):**
- Tool errors are retried automatically (up to 3 times with exponential backoff)
- Transient errors (429, 500, 503, timeouts): System handles retries - continue normally
- Non-retryable errors (400, business logic failures):
  - If `create_initial_bill_split` fails but OCR succeeded: The retry system will attempt recovery
  - If all retries fail: Use `send_error_message` with clear explanation and ask user to /new_bill
  - Example: "Failed to create bill split after multiple attempts. Please try /new_bill with a clearer photo."
- NEVER send partial/incorrect results to user
- NEVER fabricate data to work around errors
- If error persists after retries, inform user and reset gracefully

**When to save state:**
- If user sends text AND participant description is NOT PROVIDED → extract text using `get_latest_text_message`, then `save_participant_description`
- If user sends photo AND receipt is NOT UPLOADED → extract file_id using `extract_file_id_from_message`, then `save_receipt_file_id`

**Termination conditions:**
You are done when:
1. You've successfully sent the final bill split to user with `send_message`, OR
2. You've sent an error message with `send_error_message` and told them to retry with /new_bill

After completion, return your final response WITHOUT any more tool calls. The system will handle session reset.

**Example workflow (optimized for parallel execution):**
1. Check state → description missing → request_participant_description → STOP
2. User sends text → save description + request_receipt_photo (parallel) → STOP
3. User sends photo → save_file_id + download_photo + send_status (parallel)
4. extract_receipt_ocr → create_bill_split
5. Verification: [calculate_totals, calculate_discrepancy, check_accuracy, find_unassigned] (parallel) → all pass
6. send_message with final result → DONE

Target: 3-4 iterations for standard flow

Think step-by-step and use tools strategically to accomplish the bill splitting task."""


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
        parts.append(f"\n**New input from user:**\n{new_message}")
    else:
        parts.append(
            "\n**Trigger:** User executed /new_bill command to start a new bill splitting session."
        )

    parts.append(
        "\n**Your task:** Analyze the current state and decide what actions to take. Use the appropriate tools to accomplish your goal."
    )

    return "\n".join(parts)
