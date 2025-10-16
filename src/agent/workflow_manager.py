"""Workflow manager for deterministic orchestration of bill splitting.

This module handles predictable scenarios with fixed logic before delegating to
the agent for complex decision-making. This hybrid approach improves:
- Performance: Fewer LLM calls for standard flows
- Reliability: Deterministic behavior for predictable scenarios
- Flexibility: Agent still handles edge cases and ambiguous inputs
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.observability.phoenix import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("cheqmate.workflow")


class WorkflowManager:
    """Manages deterministic workflow steps before delegating to agent."""

    async def handle_new_bill_command(
        self, chat_id: int, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """
        Handle /new_bill command deterministically.

        Flow:
        1. Reset session
        2. Request participant description
        3. Return without invoking agent

        Args:
            chat_id: Telegram chat ID
            context: Telegram context

        Returns:
            True if handled deterministically (no agent needed)
        """
        with tracer.start_as_current_span(
            "workflow_new_bill", openinference_span_kind="chain"
        ) as span:
            span.set_attribute("workflow.action", "new_bill_command")
            span.set_attribute("workflow.deterministic", True)

            logger.info(
                f"Workflow handling /new_bill for chat {chat_id} (deterministic)"
            )

            # Import here to avoid circular dependency
            from src.bot.conversation_manager import conversation_manager
            from src.tools.user_interaction import request_participant_description

            # Reset session
            session = conversation_manager.get_session(chat_id)
            session.reset()

            # Request participant description
            await request_participant_description(chat_id, context)

            logger.info(
                f"Workflow completed /new_bill for chat {chat_id} - no agent needed"
            )
            return True

    async def handle_photo_message(
        self,
        chat_id: int,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> tuple[bool, str | None]:
        """
        Handle photo message with deterministic logic when appropriate.

        Flow:
        - If no OCR exists: Download → OCR → Save → Send formatted receipt
        - If OCR exists: Delegate to agent (user might be correcting)

        Args:
            chat_id: Telegram chat ID
            update: Telegram update object
            context: Telegram context

        Returns:
            Tuple of (handled_deterministically, message_for_agent)
            - If handled: (True, None)
            - If needs agent: (False, message_describing_action)
        """
        with tracer.start_as_current_span(
            "workflow_photo", openinference_span_kind="chain"
        ) as span:
            span.set_attribute("workflow.action", "photo_message")

            # Import here to avoid circular dependency
            from src.bot.conversation_manager import conversation_manager
            from src.tools.user_interaction import extract_file_id_from_message

            session = conversation_manager.get_session(chat_id)
            file_id = extract_file_id_from_message(update)

            if not file_id:
                logger.warning(f"No file_id in photo message for chat {chat_id}")
                return False, None

            # Check if we already have OCR data
            if session.has_receipt_data():
                logger.info(
                    f"Chat {chat_id} already has OCR data - delegating to agent"
                )
                span.set_attribute("workflow.deterministic", False)
                span.set_attribute("workflow.reason", "has_existing_ocr")
                return False, f"[User sent a new photo with file_id: {file_id}]"

            # Deterministic flow: No OCR yet, process automatically
            logger.info(
                f"Workflow handling photo for chat {chat_id} (deterministic OCR)"
            )
            span.set_attribute("workflow.deterministic", True)

            try:
                # Import here to avoid circular dependency
                from src.tools.llm_processing import extract_receipt_ocr
                from src.tools.user_interaction import (
                    download_telegram_photo,
                    send_formatted_receipt,
                )

                # 1. Download photo
                await download_telegram_photo(chat_id, file_id, context)
                logger.debug(f"Downloaded photo for chat {chat_id}")

                # 2. Save file_id to session
                session.set_receipt(file_id)
                logger.debug(f"Saved file_id for chat {chat_id}")

                # 3. Run OCR
                receipt_data = await extract_receipt_ocr(chat_id)
                logger.info(
                    f"OCR completed for chat {chat_id}: "
                    f"{len(receipt_data.items)} items, {receipt_data.total} {receipt_data.currency}"
                )

                # 4. Save OCR results to session
                session.store_receipt_data(receipt_data)

                # 5. Send formatted receipt to user
                await send_formatted_receipt(chat_id, context)
                logger.info(f"Sent formatted receipt to chat {chat_id}")

                span.set_attribute("workflow.ocr_items_count", len(receipt_data.items))
                span.set_attribute("workflow.ocr_total", float(receipt_data.total))
                span.set_attribute("workflow.ocr_currency", receipt_data.currency)

                logger.info(
                    f"Workflow completed photo processing for chat {chat_id} - no agent needed"
                )
                return True, None

            except Exception as e:
                logger.error(
                    f"Error in workflow photo processing for chat {chat_id}: {e}",
                    exc_info=True,
                )
                # Fall back to agent on error
                span.set_attribute("workflow.error", True)
                span.set_attribute("workflow.error_message", str(e))
                return (
                    False,
                    f"[User sent a photo with file_id: {file_id}. Error during automatic processing: {e}]",
                )

    async def should_handle_text_with_agent(
        self, chat_id: int, text: str
    ) -> tuple[bool, str]:
        """
        Determine if text message should be handled by agent.

        Text messages are always handled by agent for flexibility:
        - Could be participant description
        - Could be clarification/answer
        - Could be question/instruction
        - Could be correction

        Args:
            chat_id: Telegram chat ID
            text: User's text message

        Returns:
            Tuple of (use_agent, message_for_agent)
        """
        with tracer.start_as_current_span(
            "workflow_text", openinference_span_kind="chain"
        ) as span:
            span.set_attribute("workflow.action", "text_message")
            span.set_attribute("workflow.deterministic", False)
            span.set_attribute("workflow.reason", "text_needs_interpretation")

            logger.info(
                f"Text message for chat {chat_id} will be handled by agent (requires interpretation)"
            )

            # Always delegate text to agent
            return True, text


# Global workflow manager instance
workflow_manager = WorkflowManager()
