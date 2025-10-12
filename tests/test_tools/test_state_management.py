"""Unit tests for state management tools.

These tests cover the 4 state management functions:
- get_participant_description
- get_receipt_file_id
- save_participant_description
- save_receipt_file_id
"""

from unittest.mock import Mock, patch

import pytest

from src.models.agent_state import AgentBillSession
from src.tools.state_management import (
    get_participant_description,
    get_receipt_file_id,
    save_participant_description,
    save_receipt_file_id,
)


class TestGetParticipantDescription:
    """Tests for get_participant_description function."""

    @patch("src.tools.state_management.conversation_manager")
    def test_get_description_exists(self, mock_manager):
        """Test retrieving description when it exists."""
        # Setup mock session with description
        mock_session = Mock()
        mock_session.participant_description = "Alice had burger, Bob had salad"
        mock_manager.get_session.return_value = mock_session

        result = get_participant_description(chat_id=12345)

        assert result == "Alice had burger, Bob had salad"
        mock_manager.get_session.assert_called_once_with(12345)

    @patch("src.tools.state_management.conversation_manager")
    def test_get_description_not_set(self, mock_manager):
        """Test retrieving description when it's not set."""
        # Setup mock session without description
        mock_session = Mock()
        mock_session.participant_description = None
        mock_manager.get_session.return_value = mock_session

        result = get_participant_description(chat_id=12345)

        assert result is None
        mock_manager.get_session.assert_called_once_with(12345)


class TestGetReceiptFileId:
    """Tests for get_receipt_file_id function."""

    @patch("src.tools.state_management.conversation_manager")
    def test_get_file_id_exists(self, mock_manager):
        """Test retrieving file ID when it exists."""
        # Setup mock session with file_id
        mock_session = Mock()
        mock_session.receipt_file_id = "file_abc123"
        mock_manager.get_session.return_value = mock_session

        result = get_receipt_file_id(chat_id=12345)

        assert result == "file_abc123"
        mock_manager.get_session.assert_called_once_with(12345)

    @patch("src.tools.state_management.conversation_manager")
    def test_get_file_id_not_set(self, mock_manager):
        """Test retrieving file ID when it's not set."""
        # Setup mock session without file_id
        mock_session = Mock()
        mock_session.receipt_file_id = None
        mock_manager.get_session.return_value = mock_session

        result = get_receipt_file_id(chat_id=12345)

        assert result is None
        mock_manager.get_session.assert_called_once_with(12345)


class TestSaveParticipantDescription:
    """Tests for save_participant_description function."""

    @patch("src.tools.state_management.conversation_manager")
    def test_save_description(self, mock_manager):
        """Test saving participant description."""
        # Setup mock session
        mock_session = Mock()
        mock_manager.get_session.return_value = mock_session

        description = "Alice had burger, Bob had salad"
        save_participant_description(chat_id=12345, description=description)

        mock_manager.get_session.assert_called_once_with(12345)
        mock_session.set_description.assert_called_once_with(description)

    @patch("src.tools.state_management.conversation_manager")
    def test_save_empty_description(self, mock_manager):
        """Test saving empty description."""
        # Setup mock session
        mock_session = Mock()
        mock_manager.get_session.return_value = mock_session

        save_participant_description(chat_id=12345, description="")

        mock_manager.get_session.assert_called_once_with(12345)
        mock_session.set_description.assert_called_once_with("")


class TestSaveReceiptFileId:
    """Tests for save_receipt_file_id function."""

    @patch("src.tools.state_management.conversation_manager")
    def test_save_file_id(self, mock_manager):
        """Test saving receipt file ID."""
        # Setup mock session
        mock_session = Mock()
        mock_manager.get_session.return_value = mock_session

        file_id = "file_abc123"
        save_receipt_file_id(chat_id=12345, file_id=file_id)

        mock_manager.get_session.assert_called_once_with(12345)
        mock_session.set_receipt.assert_called_once_with(file_id)

    @patch("src.tools.state_management.conversation_manager")
    def test_save_different_file_id(self, mock_manager):
        """Test saving different file ID."""
        # Setup mock session
        mock_session = Mock()
        mock_manager.get_session.return_value = mock_session

        file_id = "file_xyz789"
        save_receipt_file_id(chat_id=12345, file_id=file_id)

        mock_manager.get_session.assert_called_once_with(12345)
        mock_session.set_receipt.assert_called_once_with(file_id)


class TestIntegration:
    """Integration tests using real AgentBillSession."""

    @patch("src.tools.state_management.conversation_manager")
    def test_save_and_retrieve_description(self, mock_manager):
        """Test saving and then retrieving description."""
        # Use real session
        session = AgentBillSession()
        mock_manager.get_session.return_value = session

        # Save description
        description = "Alice had burger, Bob had salad"
        save_participant_description(chat_id=12345, description=description)

        # Retrieve description
        result = get_participant_description(chat_id=12345)

        assert result == description

    @patch("src.tools.state_management.conversation_manager")
    def test_save_and_retrieve_file_id(self, mock_manager):
        """Test saving and then retrieving file ID."""
        # Use real session
        session = AgentBillSession()
        mock_manager.get_session.return_value = session

        # Save file_id
        file_id = "file_abc123"
        save_receipt_file_id(chat_id=12345, file_id=file_id)

        # Retrieve file_id
        result = get_receipt_file_id(chat_id=12345)

        assert result == file_id

    @patch("src.tools.state_management.conversation_manager")
    def test_multiple_operations(self, mock_manager):
        """Test multiple save/retrieve operations."""
        # Use real session
        session = AgentBillSession()
        mock_manager.get_session.return_value = session

        # Initially empty
        assert get_participant_description(12345) is None
        assert get_receipt_file_id(12345) is None

        # Save both
        save_participant_description(12345, "Alice had burger")
        save_receipt_file_id(12345, "file_123")

        # Retrieve both
        assert get_participant_description(12345) == "Alice had burger"
        assert get_receipt_file_id(12345) == "file_123"

        # Update description
        save_participant_description(12345, "Bob had salad")
        assert get_participant_description(12345) == "Bob had salad"
        # File ID should still be there
        assert get_receipt_file_id(12345) == "file_123"
