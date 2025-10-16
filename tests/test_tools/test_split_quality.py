"""Unit tests for split_quality.py.

Tests the consolidated quality evaluation tool that replaces 4 separate
calculation tools.
"""

import pytest
from decimal import Decimal
from unittest.mock import patch

from src.models.bill import BillSplit, ParticipantItem, ParticipantShare, ReceiptItem, ReceiptData
from src.models.agent_state import AgentBillSession
from src.tools.split_quality import SplitQualityMetrics, evaluate_split_quality


@pytest.fixture(autouse=True)
def mock_conversation_manager_for_quality_tests(sample_receipt_items):
    """Auto-mock conversation_manager for all tests in this file."""
    with patch("src.tools.split_quality.conversation_manager") as mock_cm:
        # Create a session with receipt data from sample_receipt_items
        mock_session = AgentBillSession()
        total = sum(item.total_price for item in sample_receipt_items)
        mock_session.receipt_data = ReceiptData(
            items=sample_receipt_items,
            currency="USD",
            total=total
        )
        mock_cm.get_session.return_value = mock_session
        yield mock_cm


class TestEvaluateSplitQuality:
    """Test suite for evaluate_split_quality function."""

    def test_evaluate_split_quality_perfect(self, sample_receipt_data, sample_bill_split):
        """Test evaluation of a perfect split with no discrepancy."""
        # Execute
        metrics = evaluate_split_quality(12345, sample_bill_split)

        # Assert
        assert metrics.is_complete is True
        assert metrics.passes_accuracy_threshold is True
        assert metrics.total_discrepancy == Decimal("0.00")
        assert metrics.unassigned_count == 0
        assert metrics.participant_count == 2
        assert metrics.participants_sum == sample_receipt_data.total

    def test_evaluate_split_quality_with_discrepancy(
        self, sample_receipt_items
    ):
        """Test evaluation of split with missing items causing discrepancy."""
        # Setup - split missing the Fries and Soda items
        total = sum(item.total_price for item in sample_receipt_items)
        imperfect_split = BillSplit(
            participants=[
                ParticipantShare(
                    name="Alice",
                    items=[
                        ParticipantItem(
                            item_name="Burger", item_numerator=1, item_denominator=1
                        ),
                    ],
                ),
                ParticipantShare(
                    name="Bob",
                    items=[
                        ParticipantItem(
                            item_name="Salad", item_numerator=1, item_denominator=1
                        ),
                    ],
                ),
                # Missing: Fries (2x$5.00 = $10.00) and Soda (2x$3.00 = $6.00)
                # Total missing: $16.00
            ],
            receipt_items=sample_receipt_items,
            currency="USD",
            total=total,
        )

        receipt_data_obj = type('obj', (object,), {
            'items': sample_receipt_items,
            'total': total,
        })()

        # Execute
        metrics = evaluate_split_quality(12345, imperfect_split)

        # Assert
        assert metrics.is_complete is False  # Not complete due to discrepancy
        assert metrics.passes_accuracy_threshold is False  # $16.00 > 0.02
        assert metrics.total_discrepancy == Decimal("16.00")
        assert metrics.participant_count == 2
        # Alice: $15.00, Bob: $12.00, Sum: $27.00 (missing $16.00)
        assert metrics.participants_sum == Decimal("27.00")
        assert metrics.participant_totals["Alice"] == Decimal("15.00")
        assert metrics.participant_totals["Bob"] == Decimal("12.00")

    def test_evaluate_split_quality_unassigned_items(
        self, sample_receipt_items
    ):
        """Test evaluation of split with unassigned items."""
        # Setup - split assigns only Burger and Salad, leaving Fries and Soda unassigned
        total = sum(item.total_price for item in sample_receipt_items)
        split_with_unassigned = BillSplit(
            participants=[
                ParticipantShare(
                    name="Alice",
                    items=[
                        ParticipantItem(
                            item_name="Burger", item_numerator=1, item_denominator=1
                        ),
                    ],
                ),
                ParticipantShare(
                    name="Bob",
                    items=[
                        ParticipantItem(
                            item_name="Salad", item_numerator=1, item_denominator=1
                        ),
                    ],
                ),
                # Not assigning Fries or Soda
            ],
            receipt_items=sample_receipt_items,
            currency="USD",
            total=total,
        )

        receipt_data_obj = type('obj', (object,), {
            'items': sample_receipt_items,
            'total': total,
        })()

        # Execute
        metrics = evaluate_split_quality(12345, split_with_unassigned)

        # Assert
        assert metrics.is_complete is False  # Unassigned items present
        assert metrics.unassigned_count == 2  # Fries and Soda
        assert len(metrics.unassigned_items) == 2
        # Verify the unassigned items are Fries and Soda
        unassigned_names = [item.name for item in metrics.unassigned_items]
        assert "Fries" in unassigned_names
        assert "Soda" in unassigned_names

    def test_evaluate_split_quality_within_tolerance(
        self, sample_receipt_items, mock_conversation_manager_for_quality_tests
    ):
        """Test evaluation with small discrepancy within tolerance."""
        # Setup - split with tiny rounding discrepancy
        total = sum(item.total_price for item in sample_receipt_items)

        # Update the mock session's receipt_data to have the modified total
        mock_session = mock_conversation_manager_for_quality_tests.get_session.return_value
        mock_session.receipt_data.total = total + Decimal("0.01")

        # Create a split where the calculated totals differ by $0.01 from receipt
        # We'll do this by slightly modifying the receipt total
        receipt_data_obj = type('obj', (object,), {
            'items': sample_receipt_items,
            'total': total + Decimal("0.01"),  # $0.01 higher than actual sum
        })()

        perfect_split = BillSplit(
            participants=[
                ParticipantShare(
                    name="Alice",
                    items=[
                        ParticipantItem(
                            item_name="Burger", item_numerator=1, item_denominator=1
                        ),
                        ParticipantItem(
                            item_name="Fries", item_numerator=1, item_denominator=2
                        ),
                        ParticipantItem(
                            item_name="Soda", item_numerator=1, item_denominator=2
                        ),
                    ],
                ),
                ParticipantShare(
                    name="Bob",
                    items=[
                        ParticipantItem(
                            item_name="Salad", item_numerator=1, item_denominator=1
                        ),
                        ParticipantItem(
                            item_name="Fries", item_numerator=1, item_denominator=2
                        ),
                        ParticipantItem(
                            item_name="Soda", item_numerator=1, item_denominator=2
                        ),
                    ],
                ),
            ],
            receipt_items=sample_receipt_items,
            currency="USD",
            total=receipt_data_obj.total,
        )

        # Execute
        metrics = evaluate_split_quality(12345, perfect_split)

        # Assert
        assert metrics.passes_accuracy_threshold is True  # $0.01 < 0.02
        assert metrics.total_discrepancy == Decimal("0.01")
        # However, is_complete requires both accuracy AND no unassigned items
        # Since all items are assigned, this should be complete
        assert metrics.unassigned_count == 0
        assert metrics.is_complete is True


class TestSplitQualityMetrics:
    """Test suite for SplitQualityMetrics dataclass methods."""

    def test_split_quality_metrics_to_dict(self, sample_receipt_items):
        """Test conversion of metrics to dictionary."""
        # Setup
        metrics = SplitQualityMetrics(
            participant_totals={"Alice": Decimal("20.00"), "Bob": Decimal("17.00")},
            participants_sum=Decimal("37.00"),
            participant_count=2,
            receipt_total=Decimal("37.00"),
            total_discrepancy=Decimal("0.00"),
            unassigned_items=[],
            unassigned_count=0,
            passes_accuracy_threshold=True,
            is_complete=True,
        )

        # Execute
        result = metrics.to_dict()

        # Assert
        assert isinstance(result, dict)
        # Check Decimal values converted to float
        assert result["participant_totals"] == {"Alice": 20.00, "Bob": 17.00}
        assert result["participants_sum"] == 37.00
        assert result["receipt_total"] == 37.00
        assert result["total_discrepancy"] == 0.00
        assert result["participant_count"] == 2
        assert result["unassigned_count"] == 0
        assert result["unassigned_items"] == []
        assert result["passes_accuracy_threshold"] is True
        assert result["is_complete"] is True

    def test_split_quality_metrics_to_dict_with_unassigned(self, sample_receipt_items):
        """Test dictionary conversion with unassigned items."""
        # Setup
        unassigned_item = ReceiptItem(name="Fries", price=Decimal("5.00"), quantity=2)

        metrics = SplitQualityMetrics(
            participant_totals={"Alice": Decimal("20.00")},
            participants_sum=Decimal("20.00"),
            participant_count=1,
            receipt_total=Decimal("30.00"),
            total_discrepancy=Decimal("10.00"),
            unassigned_items=[unassigned_item],
            unassigned_count=1,
            passes_accuracy_threshold=False,
            is_complete=False,
        )

        # Execute
        result = metrics.to_dict()

        # Assert
        assert result["unassigned_count"] == 1
        assert len(result["unassigned_items"]) == 1
        assert result["unassigned_items"][0]["name"] == "Fries"
        assert result["unassigned_items"][0]["price"] == 5.00
        assert result["unassigned_items"][0]["quantity"] == 2
        assert result["unassigned_items"][0]["total_price"] == 10.00

    def test_split_quality_metrics_format_summary(self):
        """Test human-readable formatting of metrics."""
        # Setup
        metrics = SplitQualityMetrics(
            participant_totals={"Alice": Decimal("20.00"), "Bob": Decimal("17.00")},
            participants_sum=Decimal("37.00"),
            participant_count=2,
            receipt_total=Decimal("37.00"),
            total_discrepancy=Decimal("0.00"),
            unassigned_items=[],
            unassigned_count=0,
            passes_accuracy_threshold=True,
            is_complete=True,
        )

        # Execute
        summary = metrics.format_summary()

        # Assert
        assert isinstance(summary, str)
        assert "Alice: 20.00" in summary
        assert "Bob: 17.00" in summary
        assert "Sum**: 37.00" in summary
        assert "Receipt Total**: 37.00" in summary
        assert "Discrepancy**: 0.00" in summary
        assert "✅ PASS" in summary  # Accuracy passes
        assert "✅ None" in summary  # No unassigned items
        assert "✅ COMPLETE" in summary  # Overall complete

    def test_split_quality_metrics_format_summary_incomplete(self, sample_receipt_items):
        """Test formatting of incomplete split summary."""
        # Setup
        unassigned_item = ReceiptItem(name="Fries", price=Decimal("5.00"), quantity=2)

        metrics = SplitQualityMetrics(
            participant_totals={"Alice": Decimal("15.00")},
            participants_sum=Decimal("15.00"),
            participant_count=1,
            receipt_total=Decimal("25.00"),
            total_discrepancy=Decimal("10.00"),
            unassigned_items=[unassigned_item],
            unassigned_count=1,
            passes_accuracy_threshold=False,
            is_complete=False,
        )

        # Execute
        summary = metrics.format_summary()

        # Assert
        assert "❌ FAIL" in summary  # Accuracy fails
        assert "Unassigned Items**: 1" in summary
        assert "Fries: 10.00" in summary
        assert "❌ INCOMPLETE" in summary  # Overall incomplete


class TestEvaluateSplitQualityWithCustomTolerance:
    """Test evaluate_split_quality with custom tolerance."""

    def test_custom_tolerance_passes(self, sample_receipt_items, mock_conversation_manager_for_quality_tests):
        """Test split passes with custom (higher) tolerance."""
        # Setup - split with $0.05 discrepancy
        total = sum(item.total_price for item in sample_receipt_items)

        # Update the mock session's receipt_data to have the modified total
        mock_session = mock_conversation_manager_for_quality_tests.get_session.return_value
        mock_session.receipt_data.total = total + Decimal("0.05")

        receipt_data_obj = type('obj', (object,), {
            'items': sample_receipt_items,
            'total': total + Decimal("0.05"),
        })()

        perfect_split = BillSplit(
            participants=[
                ParticipantShare(
                    name="Alice",
                    items=[
                        ParticipantItem(
                            item_name="Burger", item_numerator=1, item_denominator=1
                        ),
                        ParticipantItem(
                            item_name="Fries", item_numerator=1, item_denominator=2
                        ),
                        ParticipantItem(
                            item_name="Soda", item_numerator=1, item_denominator=2
                        ),
                    ],
                ),
                ParticipantShare(
                    name="Bob",
                    items=[
                        ParticipantItem(
                            item_name="Salad", item_numerator=1, item_denominator=1
                        ),
                        ParticipantItem(
                            item_name="Fries", item_numerator=1, item_denominator=2
                        ),
                        ParticipantItem(
                            item_name="Soda", item_numerator=1, item_denominator=2
                        ),
                    ],
                ),
            ],
            receipt_items=sample_receipt_items,
            currency="USD",
            total=receipt_data_obj.total,
        )

        # Execute with higher tolerance
        metrics = evaluate_split_quality(
            12345, perfect_split, tolerance=Decimal("0.10")
        )

        # Assert
        assert metrics.passes_accuracy_threshold is True  # $0.05 < $0.10
        assert metrics.total_discrepancy == Decimal("0.05")

    def test_custom_tolerance_fails(self, sample_receipt_items, mock_conversation_manager_for_quality_tests):
        """Test split fails with custom (stricter) tolerance."""
        # Setup - split with $0.015 discrepancy
        total = sum(item.total_price for item in sample_receipt_items)

        # Update the mock session's receipt_data to have the modified total
        mock_session = mock_conversation_manager_for_quality_tests.get_session.return_value
        mock_session.receipt_data.total = total + Decimal("0.015")

        receipt_data_obj = type('obj', (object,), {
            'items': sample_receipt_items,
            'total': total + Decimal("0.015"),
        })()

        perfect_split = BillSplit(
            participants=[
                ParticipantShare(
                    name="Alice",
                    items=[
                        ParticipantItem(
                            item_name="Burger", item_numerator=1, item_denominator=1
                        ),
                        ParticipantItem(
                            item_name="Fries", item_numerator=1, item_denominator=2
                        ),
                        ParticipantItem(
                            item_name="Soda", item_numerator=1, item_denominator=2
                        ),
                    ],
                ),
                ParticipantShare(
                    name="Bob",
                    items=[
                        ParticipantItem(
                            item_name="Salad", item_numerator=1, item_denominator=1
                        ),
                        ParticipantItem(
                            item_name="Fries", item_numerator=1, item_denominator=2
                        ),
                        ParticipantItem(
                            item_name="Soda", item_numerator=1, item_denominator=2
                        ),
                    ],
                ),
            ],
            receipt_items=sample_receipt_items,
            currency="USD",
            total=receipt_data_obj.total,
        )

        # Execute with stricter tolerance
        metrics = evaluate_split_quality(
            12345, perfect_split, tolerance=Decimal("0.01")
        )

        # Assert
        assert metrics.passes_accuracy_threshold is False  # $0.015 > $0.01
        assert metrics.total_discrepancy == Decimal("0.015")
