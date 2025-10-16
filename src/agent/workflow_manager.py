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

    async def _try_create_initial_split_if_ready(
        self, chat_id: int, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """
        Try to create initial bill split if both receipt data and description are ready.

        This is called after either:
        1. Receipt OCR completes (check if description exists)
        2. Participant description is provided (check if OCR exists)

        Args:
            chat_id: Telegram chat ID
            context: Telegram context

        Returns:
            True if split was created successfully, False if missing data or error
        """
        # Import here to avoid circular dependency
        from src.bot.conversation_manager import conversation_manager
        from src.tools.llm_processing import create_initial_bill_split
        from src.tools.user_interaction import send_formatted_split

        session = conversation_manager.get_session(chat_id)

        # Check if we have both pieces needed
        if not session.has_receipt_data():
            logger.debug(
                f"Chat {chat_id}: Cannot create split yet - missing receipt data"
            )
            return False

        if not session.participant_description:
            logger.debug(
                f"Chat {chat_id}: Cannot create split yet - missing participant description"
            )
            return False

        # Both pieces available - create split deterministically
        logger.info(
            f"Chat {chat_id}: Both receipt data and description available - creating initial split"
        )

        try:
            # Create initial bill split using LLM
            bill_split = await create_initial_bill_split(
                chat_id, session.participant_description
            )

            # Store in session
            session.store_bill_split(bill_split)

            # Send formatted split to user
            await send_formatted_split(
                chat_id, bill_split, context, title="Initial Bill Split"
            )

            logger.info(
                f"Chat {chat_id}: Successfully created and sent initial bill split deterministically"
            )
            return True

        except Exception as e:
            logger.error(
                f"Chat {chat_id}: Error creating initial split: {e}", exc_info=True
            )
            return False

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

                # 6. Try to create initial split if participant description exists
                split_created = await self._try_create_initial_split_if_ready(
                    chat_id, context
                )
                if split_created:
                    span.set_attribute("workflow.split_auto_created", True)
                    logger.info(
                        f"Workflow completed photo processing + split creation for chat {chat_id} - no agent needed"
                    )
                else:
                    logger.info(
                        f"Workflow completed photo processing for chat {chat_id} - waiting for participant description"
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
        self, chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE
    ) -> tuple[bool, str]:
        """
        Determine if text message should be handled by agent.

        Deterministic handling:
        - If awaiting participant description: Store and try to create split

        Otherwise delegate to agent for:
        - Clarification/answer
        - Question/instruction
        - Correction

        Args:
            chat_id: Telegram chat ID
            text: User's text message
            context: Telegram context

        Returns:
            Tuple of (use_agent, message_for_agent)
        """
        with tracer.start_as_current_span(
            "workflow_text", openinference_span_kind="chain"
        ) as span:
            span.set_attribute("workflow.action", "text_message")

            # Import here to avoid circular dependency
            from src.bot.conversation_manager import conversation_manager
            from src.models.conversation_state import ConversationStep

            session = conversation_manager.get_session(chat_id)

            # Check if we're awaiting participant description
            if session.step == ConversationStep.AWAITING_DESCRIPTION:
                logger.info(
                    f"Chat {chat_id}: Text received while awaiting description - storing and trying to create split"
                )
                span.set_attribute("workflow.deterministic", True)
                span.set_attribute("workflow.reason", "storing_participant_description")

                # Store the participant description
                session.set_description(text)
                logger.debug(f"Chat {chat_id}: Stored participant description")

                # Try to create split if receipt data exists
                split_created = await self._try_create_initial_split_if_ready(
                    chat_id, context
                )

                if split_created:
                    span.set_attribute("workflow.split_auto_created", True)
                    logger.info(
                        f"Chat {chat_id}: Participant description stored + split created - no agent needed"
                    )
                    # No agent needed, split was created
                    return False, ""
                else:
                    # Split not created yet, but description stored
                    # Send message asking for receipt
                    from src.tools.user_interaction import request_receipt_photo

                    await request_receipt_photo(chat_id, context)
                    logger.info(
                        f"Chat {chat_id}: Participant description stored - waiting for receipt"
                    )
                    return False, ""

            # Not awaiting description - delegate to agent for interpretation
            span.set_attribute("workflow.deterministic", False)
            span.set_attribute("workflow.reason", "text_needs_interpretation")

            logger.info(
                f"Text message for chat {chat_id} will be handled by agent (requires interpretation)"
            )

            return True, text


# Global workflow manager instance
workflow_manager = WorkflowManager()
