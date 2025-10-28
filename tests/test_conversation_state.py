"""Tests for conversation state management."""

from src.models.bill import Receipt
from src.models.conversation_state import BillSession, ConversationStep


class TestBillSession:
    """Test suite for BillSession class."""

    def test_initialization(self):
        """Test that a new session initializes with correct default values."""
        session = BillSession()

        assert session.step == ConversationStep.IDLE
        assert session.receipt_file_id is None
        assert session.receipt_data is None
        assert session.participant_description is None
        assert not session.is_ready_for_processing()

    def test_start_new_bill(self):
        """Test starting a new bill workflow."""
        session = BillSession()
        session.start_new_bill()

        assert session.step == ConversationStep.AWAITING_BOTH
        assert session.receipt_file_id is None
        assert session.receipt_data is None
        assert session.participant_description is None

    def test_reset(self):
        """Test resetting a session clears all state."""
        session = BillSession()
        session.step = ConversationStep.PROCESSING
        session.receipt_file_id = "test_file_id"
        session.receipt_data = Receipt(
            restaurant_name="Test",
            currency="USD",
            items=[],
            total=0,
        )
        session.participant_description = "test description"

        session.reset()

        assert session.step == ConversationStep.IDLE
        assert session.receipt_file_id is None
        assert session.receipt_data is None
        assert session.participant_description is None

    def test_set_receipt_without_description(self, sample_receipt_usd: Receipt):
        """Test setting receipt when description is not yet provided."""
        session = BillSession()
        session.start_new_bill()

        session.set_receipt("file_123", sample_receipt_usd)

        assert session.receipt_file_id == "file_123"
        assert session.receipt_data == sample_receipt_usd
        assert session.step == ConversationStep.AWAITING_DESCRIPTION
        assert not session.is_ready_for_processing()

    def test_set_receipt_with_description(self, sample_receipt_usd: Receipt):
        """Test setting receipt when description already exists."""
        session = BillSession()
        session.start_new_bill()
        session.participant_description = "Alice had burger, Bob had salad"

        session.set_receipt("file_123", sample_receipt_usd)

        assert session.receipt_file_id == "file_123"
        assert session.receipt_data == sample_receipt_usd
        assert session.step == ConversationStep.PROCESSING
        assert session.is_ready_for_processing()

    def test_set_description_without_receipt(self):
        """Test setting description when receipt is not yet provided."""
        session = BillSession()
        session.start_new_bill()

        session.set_description("Alice had burger, Bob had salad")

        assert session.participant_description == "Alice had burger, Bob had salad"
        assert session.step == ConversationStep.AWAITING_RECEIPT
        assert not session.is_ready_for_processing()

    def test_set_description_with_receipt(self, sample_receipt_usd: Receipt):
        """Test setting description when receipt already exists."""
        session = BillSession()
        session.start_new_bill()
        session.receipt_file_id = "file_123"
        session.receipt_data = sample_receipt_usd

        session.set_description("Alice had burger, Bob had salad")

        assert session.participant_description == "Alice had burger, Bob had salad"
        assert session.step == ConversationStep.PROCESSING
        assert session.is_ready_for_processing()

    def test_receipt_first_then_description(self, sample_receipt_usd: Receipt):
        """Test workflow: receipt provided first, then description."""
        session = BillSession()
        session.start_new_bill()

        # Step 1: Provide receipt
        session.set_receipt("file_123", sample_receipt_usd)
        assert session.step == ConversationStep.AWAITING_DESCRIPTION
        assert not session.is_ready_for_processing()

        # Step 2: Provide description
        session.set_description("Alice had burger")
        assert session.step == ConversationStep.PROCESSING
        assert session.is_ready_for_processing()

    def test_description_first_then_receipt(self, sample_receipt_usd: Receipt):
        """Test workflow: description provided first, then receipt."""
        session = BillSession()
        session.start_new_bill()

        # Step 1: Provide description
        session.set_description("Alice had burger")
        assert session.step == ConversationStep.AWAITING_RECEIPT
        assert not session.is_ready_for_processing()

        # Step 2: Provide receipt
        session.set_receipt("file_123", sample_receipt_usd)
        assert session.step == ConversationStep.PROCESSING
        assert session.is_ready_for_processing()

    def test_is_ready_for_processing_requires_all_data(
        self, sample_receipt_usd: Receipt
    ):
        """Test that is_ready_for_processing requires all data."""
        session = BillSession()

        # No data
        assert not session.is_ready_for_processing()

        # Only receipt
        session.receipt_data = sample_receipt_usd
        assert not session.is_ready_for_processing()

        # Only description
        session.receipt_data = None
        session.participant_description = "test"
        assert not session.is_ready_for_processing()

        # Both but wrong step
        session.receipt_data = sample_receipt_usd
        session.participant_description = "test"
        session.step = ConversationStep.AWAITING_BOTH
        assert not session.is_ready_for_processing()

        # All conditions met
        session.step = ConversationStep.PROCESSING
        assert session.is_ready_for_processing()

    def test_reset_after_processing(self, sample_receipt_usd: Receipt):
        """Test that reset works after completing a workflow."""
        session = BillSession()
        session.start_new_bill()
        session.set_receipt("file_123", sample_receipt_usd)
        session.set_description("Alice had burger")

        assert session.is_ready_for_processing()

        session.reset()

        assert session.step == ConversationStep.IDLE
        assert not session.is_ready_for_processing()
