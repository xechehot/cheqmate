"""Unit tests for workflow_manager.py.

Tests the deterministic workflow layer that handles predictable scenarios
without invoking the agent.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import importlib.util
import sys
from pathlib import Path

# Load workflow_manager directly without triggering agent.__init__
def load_workflow_manager():
    module_path = Path(__file__).parent.parent.parent / "src" / "agent" / "workflow_manager.py"
    spec = importlib.util.spec_from_file_location("workflow_manager_module", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules['workflow_manager_module'] = module
    spec.loader.exec_module(module)
    return module

workflow_manager_module = load_workflow_manager()
WorkflowManager = workflow_manager_module.WorkflowManager
workflow_manager = workflow_manager_module.workflow_manager

from src.models.agent_state import AgentBillSession


class TestHandleNewBillCommand:
    """Test suite for handle_new_bill_command."""

    @pytest.mark.asyncio
    @patch("src.bot.conversation_manager.conversation_manager")
    @patch("src.tools.user_interaction.request_participant_description")
    async def test_handle_new_bill_success(
        self,
        mock_request_desc,
        mock_conv_manager,
        mock_telegram_context,
    ):
        """Test /new_bill resets session and requests description."""
        # Setup
        session = AgentBillSession()
        session.participant_description = "Old data"  # Simulate existing state
        mock_conv_manager.get_session.return_value = session
        mock_request_desc.return_value = None  # Async function

        # Execute
        workflow = WorkflowManager()
        result = await workflow.handle_new_bill_command(
            chat_id=12345,
            context=mock_telegram_context,
        )

        # Assert
        assert result is True  # Handled deterministically
        assert session.participant_description is None  # Session reset
        mock_conv_manager.get_session.assert_called_once_with(12345)
        mock_request_desc.assert_called_once_with(12345, mock_telegram_context)

    @pytest.mark.asyncio
    @patch("src.bot.conversation_manager.conversation_manager")
    @patch("src.tools.user_interaction.request_participant_description")
    async def test_handle_new_bill_resets_all_state(
        self,
        mock_request_desc,
        mock_conv_manager,
        mock_telegram_context,
        sample_receipt_data,
        sample_bill_split,
    ):
        """Test /new_bill clears receipt data, split, and cached image."""
        # Setup - populate session with data
        session = AgentBillSession()
        session.participant_description = "Alice had burger"
        session.receipt_file_id = "file_123"
        session.receipt_data = sample_receipt_data
        session.bill_split = sample_bill_split
        session.image_bytes = b"fake_image"
        mock_conv_manager.get_session.return_value = session
        mock_request_desc.return_value = None

        # Execute
        workflow = WorkflowManager()
        await workflow.handle_new_bill_command(12345, mock_telegram_context)

        # Assert - all state cleared
        assert session.participant_description is None
        assert session.receipt_file_id is None
        assert session.receipt_data is None
        assert session.bill_split is None
        assert session.image_bytes is None


class TestHandlePhotoMessage:
    """Test suite for handle_photo_message."""

    @pytest.mark.asyncio
    @patch("src.bot.conversation_manager.conversation_manager")
    @patch("src.tools.user_interaction.download_telegram_photo")
    @patch("src.tools.llm_processing.extract_receipt_ocr")
    @patch("src.tools.user_interaction.send_formatted_receipt")
    @patch("src.tools.user_interaction.extract_file_id_from_message")
    async def test_handle_photo_no_ocr_deterministic(
        self,
        mock_extract_file_id,
        mock_send_receipt,
        mock_extract_ocr,
        mock_download_photo,
        mock_conv_manager,
        mock_telegram_update,
        mock_telegram_context,
        sample_receipt_data,
    ):
        """Test photo handling when no OCR exists - should process deterministically."""
        # Setup
        session = AgentBillSession()
        mock_conv_manager.get_session.return_value = session

        # Mock file_id extraction
        mock_extract_file_id.return_value = "file_abc123"

        # Mock OCR returning receipt data
        mock_extract_ocr.return_value = sample_receipt_data

        # Execute
        workflow = WorkflowManager()
        handled, message = await workflow.handle_photo_message(
            chat_id=12345,
            update=mock_telegram_update,
            context=mock_telegram_context,
        )

        # Assert
        assert handled is True  # Handled deterministically
        assert message is None  # No message for agent

        # Verify workflow steps
        mock_download_photo.assert_called_once_with(
            12345, "file_abc123", mock_telegram_context
        )
        assert session.receipt_file_id == "file_abc123"  # File ID saved
        mock_extract_ocr.assert_called_once_with(12345)
        assert session.receipt_data == sample_receipt_data  # OCR data saved
        mock_send_receipt.assert_called_once_with(
            12345, mock_telegram_context
        )

    @pytest.mark.asyncio
    @patch("src.bot.conversation_manager.conversation_manager")
    @patch("src.tools.user_interaction.download_telegram_photo")
    @patch("src.tools.llm_processing.extract_receipt_ocr")
    @patch("src.tools.user_interaction.extract_file_id_from_message")
    async def test_handle_photo_existing_ocr_delegate_to_agent(
        self,
        mock_extract_file_id,
        mock_extract_ocr,
        mock_download_photo,
        mock_conv_manager,
        mock_telegram_update,
        mock_telegram_context,
        sample_receipt_data,
    ):
        """Test photo handling when OCR already exists - should delegate to agent."""
        # Setup - session already has OCR data
        session = AgentBillSession()
        session.receipt_data = sample_receipt_data
        mock_conv_manager.get_session.return_value = session

        # Mock file_id
        mock_extract_file_id.return_value = "file_xyz789"

        # Execute
        workflow = WorkflowManager()
        handled, message = await workflow.handle_photo_message(
            chat_id=12345,
            update=mock_telegram_update,
            context=mock_telegram_context,
        )

        # Assert
        assert handled is False  # Not handled deterministically
        assert message == "[User sent a new photo with file_id: file_xyz789]"

        # Verify OCR was NOT called (already exists)
        mock_download_photo.assert_not_called()
        mock_extract_ocr.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.bot.conversation_manager.conversation_manager")
    @patch("src.tools.user_interaction.download_telegram_photo")
    @patch("src.tools.llm_processing.extract_receipt_ocr")
    @patch("src.tools.user_interaction.extract_file_id_from_message")
    async def test_handle_photo_ocr_error_fallback(
        self,
        mock_extract_file_id,
        mock_extract_ocr,
        mock_download_photo,
        mock_conv_manager,
        mock_telegram_update,
        mock_telegram_context,
    ):
        """Test photo handling when OCR fails - should fallback to agent."""
        # Setup
        session = AgentBillSession()
        mock_conv_manager.get_session.return_value = session

        # Mock file_id
        mock_extract_file_id.return_value = "file_abc123"

        # Mock OCR failure
        mock_extract_ocr.side_effect = ValueError("OCR parsing failed")

        # Execute
        workflow = WorkflowManager()
        handled, message = await workflow.handle_photo_message(
            chat_id=12345,
            update=mock_telegram_update,
            context=mock_telegram_context,
        )

        # Assert
        assert handled is False  # Delegate to agent on error
        assert "Error during automatic processing" in message
        assert "OCR parsing failed" in message

    @pytest.mark.asyncio
    @patch("src.tools.user_interaction.extract_file_id_from_message")
    async def test_handle_photo_no_file_id(
        self,
        mock_extract_file_id,
        mock_telegram_update,
        mock_telegram_context,
    ):
        """Test photo handling when no file_id can be extracted."""
        # Setup - no file_id
        mock_extract_file_id.return_value = None

        # Execute
        workflow = WorkflowManager()
        handled, message = await workflow.handle_photo_message(
            chat_id=12345,
            update=mock_telegram_update,
            context=mock_telegram_context,
        )

        # Assert
        assert handled is False
        assert message is None

    @pytest.mark.asyncio
    @patch("src.bot.conversation_manager.conversation_manager")
    @patch("src.tools.user_interaction.download_telegram_photo")
    @patch("src.tools.llm_processing.extract_receipt_ocr")
    @patch("src.tools.user_interaction.send_formatted_receipt")
    @patch("src.tools.llm_processing.create_initial_bill_split")
    @patch("src.tools.user_interaction.send_formatted_split")
    @patch("src.tools.user_interaction.extract_file_id_from_message")
    async def test_handle_photo_with_description_creates_split(
        self,
        mock_extract_file_id,
        mock_send_split,
        mock_create_split,
        mock_send_receipt,
        mock_extract_ocr,
        mock_download_photo,
        mock_conv_manager,
        mock_telegram_update,
        mock_telegram_context,
        sample_receipt_data,
        sample_bill_split,
    ):
        """Test photo handling when participant description exists - should create split."""
        # Setup - session already has participant description
        session = AgentBillSession()
        session.participant_description = "Alice had burger, Bob had salad"
        mock_conv_manager.get_session.return_value = session

        # Mock file_id extraction
        mock_extract_file_id.return_value = "file_abc123"

        # Mock OCR returning receipt data
        mock_extract_ocr.return_value = sample_receipt_data

        # Mock split creation
        mock_create_split.return_value = sample_bill_split

        # Execute
        workflow = WorkflowManager()
        handled, message = await workflow.handle_photo_message(
            chat_id=12345,
            update=mock_telegram_update,
            context=mock_telegram_context,
        )

        # Assert
        assert handled is True  # Handled deterministically
        assert message is None  # No message for agent

        # Verify OCR workflow
        mock_download_photo.assert_called_once_with(
            12345, "file_abc123", mock_telegram_context
        )
        mock_extract_ocr.assert_called_once_with(12345)
        assert session.receipt_data == sample_receipt_data
        mock_send_receipt.assert_called_once_with(12345, mock_telegram_context)

        # Verify split creation
        mock_create_split.assert_called_once_with(
            12345, "Alice had burger, Bob had salad"
        )
        mock_send_split.assert_called_once_with(
            12345, sample_bill_split, mock_telegram_context, title="Initial Bill Split"
        )
        assert session.bill_split == sample_bill_split


class TestShouldHandleTextWithAgent:
    """Test suite for should_handle_text_with_agent."""

    @pytest.mark.asyncio
    @patch("src.bot.conversation_manager.conversation_manager")
    async def test_text_not_awaiting_description_uses_agent(
        self, mock_conv_manager, mock_telegram_context
    ):
        """Test text messages use agent when not awaiting description."""
        from src.models.conversation_state import ConversationStep

        # Setup - session not awaiting description
        session = AgentBillSession()
        session.step = ConversationStep.IDLE
        mock_conv_manager.get_session.return_value = session

        workflow = WorkflowManager()

        # Various text inputs that should go to agent
        test_texts = [
            "Can you split this differently?",
            "Yes",
            "I meant 3 burgers not 2",
        ]

        for text in test_texts:
            use_agent, message = await workflow.should_handle_text_with_agent(
                chat_id=12345,
                text=text,
                context=mock_telegram_context,
            )
            assert use_agent is True
            assert message == text

    @pytest.mark.asyncio
    @patch("src.bot.conversation_manager.conversation_manager")
    @patch("src.tools.user_interaction.request_receipt_photo")
    async def test_text_awaiting_description_no_receipt_deterministic(
        self, mock_request_receipt, mock_conv_manager, mock_telegram_context
    ):
        """Test text is stored deterministically when awaiting description and no receipt."""
        from src.models.conversation_state import ConversationStep

        # Setup - session awaiting description, no receipt data
        session = AgentBillSession()
        session.step = ConversationStep.AWAITING_DESCRIPTION
        mock_conv_manager.get_session.return_value = session
        mock_request_receipt.return_value = None

        workflow = WorkflowManager()
        text = "Alice had burger, Bob had salad"

        use_agent, message = await workflow.should_handle_text_with_agent(
            chat_id=12345,
            text=text,
            context=mock_telegram_context,
        )

        # Assert - handled deterministically, no agent needed
        assert use_agent is False
        assert session.participant_description == text
        mock_request_receipt.assert_called_once_with(12345, mock_telegram_context)

    @pytest.mark.asyncio
    @patch("src.bot.conversation_manager.conversation_manager")
    @patch("src.tools.llm_processing.create_initial_bill_split")
    @patch("src.tools.user_interaction.send_formatted_split")
    async def test_text_awaiting_description_with_receipt_creates_split(
        self,
        mock_send_split,
        mock_create_split,
        mock_conv_manager,
        mock_telegram_context,
        sample_receipt_data,
        sample_bill_split,
    ):
        """Test text creates split when awaiting description and receipt exists."""
        from src.models.conversation_state import ConversationStep

        # Setup - session awaiting description WITH receipt data
        session = AgentBillSession()
        session.step = ConversationStep.AWAITING_DESCRIPTION
        session.receipt_data = sample_receipt_data
        mock_conv_manager.get_session.return_value = session
        mock_create_split.return_value = sample_bill_split
        mock_send_split.return_value = None

        workflow = WorkflowManager()
        text = "Alice had burger, Bob had salad"

        use_agent, message = await workflow.should_handle_text_with_agent(
            chat_id=12345,
            text=text,
            context=mock_telegram_context,
        )

        # Assert - handled deterministically, split created
        assert use_agent is False
        assert session.participant_description == text
        mock_create_split.assert_called_once_with(12345, text)
        mock_send_split.assert_called_once_with(
            12345, sample_bill_split, mock_telegram_context, title="Initial Bill Split"
        )
        assert session.bill_split == sample_bill_split


class TestWorkflowManagerInstance:
    """Test the global workflow_manager instance."""

    def test_workflow_manager_singleton_exists(self):
        """Test that global workflow_manager instance exists."""
        assert workflow_manager is not None
        assert isinstance(workflow_manager, WorkflowManager)
