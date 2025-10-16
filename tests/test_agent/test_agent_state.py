"""Unit tests for AgentBillSession state management.

Tests the extended session state tracking including:
- Split quality metrics storage and retrieval
- Split refinement count tracking
- State reset behavior
"""

import pytest
from decimal import Decimal

from src.models.agent_state import AgentBillSession
from src.models.bill import BillSplit, ParticipantShare, ParticipantItem, ReceiptItem
from src.tools.split_quality import SplitQualityMetrics


@pytest.fixture
def session():
    """Create a fresh AgentBillSession for each test."""
    return AgentBillSession()


@pytest.fixture
def sample_quality_metrics():
    """Create sample quality metrics for testing."""
    return SplitQualityMetrics(
        participant_totals={"Alice": Decimal("15.00"), "Bob": Decimal("22.00")},
        participants_sum=Decimal("37.00"),
        participant_count=2,
        receipt_total=Decimal("37.00"),
        total_discrepancy=Decimal("0.00"),
        unassigned_items=[],
        unassigned_count=0,
        passes_accuracy_threshold=True,
        is_complete=True,
    )


@pytest.fixture
def sample_quality_metrics_with_issues():
    """Create quality metrics with issues (discrepancy and unassigned items)."""
    unassigned_item = ReceiptItem(
        name="Dessert",
        price=Decimal("8.00"),
        quantity=1,
    )

    return SplitQualityMetrics(
        participant_totals={"Alice": Decimal("15.00"), "Bob": Decimal("22.00")},
        participants_sum=Decimal("37.00"),
        participant_count=2,
        receipt_total=Decimal("45.00"),
        total_discrepancy=Decimal("8.00"),
        unassigned_items=[unassigned_item],
        unassigned_count=1,
        passes_accuracy_threshold=False,
        is_complete=False,
    )


class TestSplitQualityMetricsStorage:
    """Test suite for split quality metrics storage and retrieval."""

    def test_initial_state_no_metrics(self, session):
        """Test that session starts with no quality metrics."""
        assert session.split_quality_metrics is None
        assert session.has_split_quality_metrics() is False

    def test_store_quality_metrics(self, session, sample_quality_metrics):
        """Test storing quality metrics in session."""
        session.store_split_quality_metrics(sample_quality_metrics)

        assert session.split_quality_metrics is not None
        assert session.has_split_quality_metrics() is True
        assert session.split_quality_metrics == sample_quality_metrics

    def test_store_quality_metrics_with_issues(
        self, session, sample_quality_metrics_with_issues
    ):
        """Test storing quality metrics with discrepancy and unassigned items."""
        session.store_split_quality_metrics(sample_quality_metrics_with_issues)

        assert session.has_split_quality_metrics() is True
        metrics = session.split_quality_metrics
        assert metrics.total_discrepancy == Decimal("8.00")
        assert metrics.unassigned_count == 1
        assert metrics.passes_accuracy_threshold is False
        assert metrics.is_complete is False

    def test_store_quality_metrics_overwrites_previous(
        self, session, sample_quality_metrics, sample_quality_metrics_with_issues
    ):
        """Test that storing new metrics overwrites previous ones."""
        # Store first metrics
        session.store_split_quality_metrics(sample_quality_metrics)
        assert session.split_quality_metrics.is_complete is True

        # Store new metrics (with issues)
        session.store_split_quality_metrics(sample_quality_metrics_with_issues)
        assert session.split_quality_metrics.is_complete is False
        assert session.split_quality_metrics.total_discrepancy == Decimal("8.00")

    def test_quality_metrics_persists_across_operations(
        self, session, sample_quality_metrics
    ):
        """Test that quality metrics persist when other session operations occur."""
        from src.models.bill import ReceiptData, BillSplit

        # Store quality metrics
        session.store_split_quality_metrics(sample_quality_metrics)

        # Perform other session operations
        session.set_description("Alice had burger")
        session.set_receipt("file_123")

        receipt_data = ReceiptData(
            items=[ReceiptItem(name="Burger", price=Decimal("15.00"), quantity=1)],
            currency="USD",
            total=Decimal("15.00"),
        )
        session.store_receipt_data(receipt_data)

        # Quality metrics should still be there
        assert session.has_split_quality_metrics() is True
        assert session.split_quality_metrics == sample_quality_metrics


class TestSplitRefinementTracking:
    """Test suite for split refinement count tracking."""

    def test_initial_state_no_refinements(self, session):
        """Test that session starts with refinement count of 0."""
        assert session.split_refinement_count == 0
        assert session.has_refined_split() is False

    def test_increment_refinement_count_once(self, session):
        """Test incrementing refinement count once."""
        session.increment_refinement_count()

        assert session.split_refinement_count == 1
        assert session.has_refined_split() is True

    def test_increment_refinement_count_multiple_times(self, session):
        """Test incrementing refinement count multiple times."""
        session.increment_refinement_count()
        session.increment_refinement_count()
        session.increment_refinement_count()

        assert session.split_refinement_count == 3
        assert session.has_refined_split() is True

    def test_refinement_count_persists_across_operations(self, session):
        """Test that refinement count persists when other session operations occur."""
        from src.models.bill import BillSplit, ParticipantShare

        # Increment refinement count
        session.increment_refinement_count()
        session.increment_refinement_count()

        # Perform other session operations
        session.set_description("Alice had burger, Bob had salad")

        bill_split = BillSplit(
            participants=[
                ParticipantShare(
                    name="Alice",
                    items=[
                        ParticipantItem(
                            item_name="Burger",
                            item_numerator=1,
                            item_denominator=1,
                        )
                    ],
                )
            ],
            receipt_items=[],
        )
        session.store_bill_split(bill_split)

        # Refinement count should still be 2
        assert session.split_refinement_count == 2
        assert session.has_refined_split() is True


class TestSessionReset:
    """Test suite for session reset behavior with new state fields."""

    def test_reset_clears_quality_metrics(self, session, sample_quality_metrics):
        """Test that reset() clears split quality metrics."""
        # Set up session with quality metrics
        session.store_split_quality_metrics(sample_quality_metrics)
        assert session.has_split_quality_metrics() is True

        # Reset session
        session.reset()

        # Quality metrics should be cleared
        assert session.split_quality_metrics is None
        assert session.has_split_quality_metrics() is False

    def test_reset_clears_refinement_count(self, session):
        """Test that reset() clears refinement count."""
        # Set up session with refinements
        session.increment_refinement_count()
        session.increment_refinement_count()
        assert session.split_refinement_count == 2

        # Reset session
        session.reset()

        # Refinement count should be 0
        assert session.split_refinement_count == 0
        assert session.has_refined_split() is False

    def test_reset_clears_all_state_including_new_fields(
        self, session, sample_quality_metrics
    ):
        """Test that reset() clears all state including new quality and refinement fields."""
        from src.models.bill import ReceiptData, BillSplit, ParticipantShare, ReceiptItem

        # Populate ALL session fields
        session.set_description("Alice had burger, Bob had salad")
        session.set_receipt("file_123")

        receipt_data = ReceiptData(
            items=[ReceiptItem(name="Burger", price=Decimal("15.00"), quantity=1)],
            currency="USD",
            total=Decimal("15.00"),
        )
        session.store_receipt_data(receipt_data)

        bill_split = BillSplit(
            participants=[
                ParticipantShare(
                    name="Alice",
                    items=[
                        ParticipantItem(
                            item_name="Burger",
                            item_numerator=1,
                            item_denominator=1,
                        )
                    ],
                )
            ],
            receipt_items=receipt_data.items,
        )
        session.store_bill_split(bill_split)

        session.store_image_bytes(b"fake_image_data")
        session.store_split_quality_metrics(sample_quality_metrics)
        session.increment_refinement_count()
        session.increment_refinement_count()

        # Verify everything is set
        assert session.participant_description is not None
        assert session.receipt_file_id is not None
        assert session.receipt_data is not None
        assert session.bill_split is not None
        assert session.image_bytes is not None
        assert session.split_quality_metrics is not None
        assert session.split_refinement_count == 2

        # Reset session
        session.reset()

        # Verify everything is cleared
        assert session.participant_description is None
        assert session.receipt_file_id is None
        assert session.receipt_data is None
        assert session.bill_split is None
        assert session.image_bytes is None
        assert session.split_quality_metrics is None
        assert session.split_refinement_count == 0


class TestStateIntegration:
    """Integration tests for quality metrics and refinement tracking together."""

    def test_typical_workflow_with_refinement(
        self, session, sample_quality_metrics_with_issues, sample_quality_metrics
    ):
        """Test a typical workflow: initial split, quality check, refinement, re-check."""
        from src.models.bill import BillSplit, ParticipantShare, ReceiptData, ReceiptItem

        # 1. Create initial split
        initial_split = BillSplit(
            participants=[
                ParticipantShare(
                    name="Alice",
                    items=[
                        ParticipantItem(
                            item_name="Burger",
                            item_numerator=1,
                            item_denominator=1,
                        )
                    ],
                )
            ],
            receipt_items=[],
        )
        session.store_bill_split(initial_split)
        assert session.has_bill_split() is True
        assert session.split_refinement_count == 0

        # 2. Evaluate quality (has issues)
        session.store_split_quality_metrics(sample_quality_metrics_with_issues)
        assert session.has_split_quality_metrics() is True
        assert session.split_quality_metrics.is_complete is False

        # 3. Refine split
        session.increment_refinement_count()
        assert session.split_refinement_count == 1
        assert session.has_refined_split() is True

        refined_split = BillSplit(
            participants=[
                ParticipantShare(
                    name="Alice",
                    items=[
                        ParticipantItem(
                            item_name="Burger",
                            item_numerator=1,
                            item_denominator=1,
                        )
                    ],
                ),
                ParticipantShare(
                    name="Bob",
                    items=[
                        ParticipantItem(
                            item_name="Dessert",
                            item_numerator=1,
                            item_denominator=1,
                        )
                    ],
                ),
            ],
            receipt_items=[],
        )
        session.store_bill_split(refined_split)

        # 4. Re-evaluate quality (now complete)
        session.store_split_quality_metrics(sample_quality_metrics)
        assert session.split_quality_metrics.is_complete is True
        assert session.split_refinement_count == 1  # Still 1 refinement

    def test_multiple_refinements_tracked(self, session):
        """Test that multiple refinements are tracked correctly."""
        # Refine multiple times
        session.increment_refinement_count()
        assert session.split_refinement_count == 1

        session.increment_refinement_count()
        assert session.split_refinement_count == 2

        session.increment_refinement_count()
        assert session.split_refinement_count == 3

        assert session.has_refined_split() is True
