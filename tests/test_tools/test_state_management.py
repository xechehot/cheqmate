"""Unit tests for state management tools.

These tests cover the 4 state management functions:
- get_participant_description
- get_receipt_file_id
- update_participant_description (async, with intelligent merging)
- save_receipt_file_id
"""

from unittest.mock import Mock, patch

import pytest

from src.models.agent_state import AgentBillSession
from src.tools.state_management import (
    get_participant_description,
    get_receipt_file_id,
    save_receipt_file_id,
    update_participant_description,
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


class TestUpdateParticipantDescription:
    """Tests for update_participant_description function (async with merge)."""

    @pytest.mark.asyncio
    @patch("src.tools.state_management.conversation_manager")
    async def test_update_first_time_no_merge(self, mock_manager):
        """Test updating description when no existing description (no LLM call)."""
        # Setup mock session with no existing description
        mock_session = Mock()
        mock_session.participant_description = None
        mock_manager.get_session.return_value = mock_session

        description = "Alice had burger, Bob had salad"
        await update_participant_description(chat_id=12345, description=description)

        # Verify: session.set_description called directly (no merge)
        mock_manager.get_session.assert_called_once_with(12345)
        mock_session.set_description.assert_called_once_with(description)

    @pytest.mark.asyncio
    @patch("src.tools.state_management.merge_participant_descriptions")
    @patch("src.tools.state_management.conversation_manager")
    async def test_update_with_existing_calls_merge(
        self, mock_manager, mock_merge_descriptions
    ):
        """Test updating description when existing exists (calls LLM merge)."""
        from unittest.mock import AsyncMock

        # Setup mock session with existing description
        mock_session = Mock()
        mock_session.participant_description = "Alice had burger"
        mock_manager.get_session.return_value = mock_session

        # Mock merge function as async
        async def mock_merge(*args, **kwargs):
            return "Alice had burger, Bob had salad"

        mock_merge_descriptions.side_effect = mock_merge

        new_description = "Bob had salad"
        await update_participant_description(chat_id=12345, description=new_description)

        # Verify: merge was called with correct arguments
        mock_merge_descriptions.assert_called_once_with(
            12345, "Alice had burger", "Bob had salad"
        )
        # Verify: merged result was stored
        mock_session.set_description.assert_called_once_with(
            "Alice had burger, Bob had salad"
        )

    @pytest.mark.asyncio
    @patch("src.tools.state_management.merge_participant_descriptions")
    @patch("src.tools.state_management.conversation_manager")
    async def test_update_stores_merged_result(
        self, mock_manager, mock_merge_descriptions
    ):
        """Test that merged result is correctly stored."""
        from unittest.mock import AsyncMock

        # Setup mock session
        mock_session = Mock()
        mock_session.participant_description = "Alice had burger"
        mock_manager.get_session.return_value = mock_session

        # Mock merge to return a specific merged result
        merged_result = "Alice had pasta, Bob had salad"

        async def mock_merge(*args, **kwargs):
            return merged_result

        mock_merge_descriptions.side_effect = mock_merge

        await update_participant_description(
            chat_id=12345, description="Actually Alice had pasta. Bob had salad"
        )

        # Verify the merged result was stored
        mock_session.set_description.assert_called_once_with(merged_result)

    @pytest.mark.asyncio
    @patch("src.tools.state_management.conversation_manager")
    async def test_update_preserves_other_state(self, mock_manager):
        """Test that updating description doesn't affect receipt_file_id."""
        # Setup mock session with both description and file_id
        mock_session = Mock()
        mock_session.participant_description = None
        mock_session.receipt_file_id = "file_123"
        mock_manager.get_session.return_value = mock_session

        await update_participant_description(
            chat_id=12345, description="Alice had burger"
        )

        # Verify: file_id unchanged
        assert mock_session.receipt_file_id == "file_123"
        # Verify: only set_description was called
        mock_session.set_description.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.tools.state_management.merge_participant_descriptions")
    @patch("src.tools.state_management.conversation_manager")
    async def test_update_with_empty_string(
        self, mock_manager, mock_merge_descriptions
    ):
        """Test updating with empty string when no existing description."""
        # Setup mock session
        mock_session = Mock()
        mock_session.participant_description = None
        mock_manager.get_session.return_value = mock_session

        await update_participant_description(chat_id=12345, description="")

        # Should just set empty (no merge needed)
        mock_session.set_description.assert_called_once_with("")
        mock_merge_descriptions.assert_not_called()


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

    @pytest.mark.asyncio
    @patch("src.tools.state_management.conversation_manager")
    async def test_update_and_retrieve_description(self, mock_manager):
        """Test updating and then retrieving description."""
        # Use real session
        session = AgentBillSession()
        mock_manager.get_session.return_value = session

        # Update description (first time, no merge)
        description = "Alice had burger, Bob had salad"
        await update_participant_description(chat_id=12345, description=description)

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

    @pytest.mark.asyncio
    @patch("src.tools.state_management.merge_participant_descriptions")
    @patch("src.tools.state_management.conversation_manager")
    async def test_multiple_updates_accumulate(
        self, mock_manager, mock_merge_descriptions
    ):
        """Test multiple updates with merging."""
        from unittest.mock import AsyncMock

        # Use real session
        session = AgentBillSession()
        mock_manager.get_session.return_value = session

        # Initially empty
        assert get_participant_description(12345) is None
        assert get_receipt_file_id(12345) is None

        # First update: no existing, direct set
        await update_participant_description(12345, "Alice had burger")
        assert get_participant_description(12345) == "Alice had burger"

        # Second update: has existing, should merge
        async def mock_merge_2(*args, **kwargs):
            return "Alice had burger, Bob had salad"

        mock_merge_descriptions.side_effect = mock_merge_2
        await update_participant_description(12345, "Bob had salad")
        assert get_participant_description(12345) == "Alice had burger, Bob had salad"
        mock_merge_descriptions.assert_called_once_with(
            12345, "Alice had burger", "Bob had salad"
        )

        # Third update: merge again
        mock_merge_descriptions.reset_mock()

        async def mock_merge_3(*args, **kwargs):
            return "Alice had pasta, Bob had salad"

        mock_merge_descriptions.side_effect = mock_merge_3
        await update_participant_description(12345, "Actually Alice had pasta")
        assert get_participant_description(12345) == "Alice had pasta, Bob had salad"
        mock_merge_descriptions.assert_called_once_with(
            12345, "Alice had burger, Bob had salad", "Actually Alice had pasta"
        )

        # Verify file operations still work
        save_receipt_file_id(12345, "file_123")
        assert get_receipt_file_id(12345) == "file_123"
