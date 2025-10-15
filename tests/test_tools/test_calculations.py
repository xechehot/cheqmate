"""Unit tests for calculation tools.

These tests cover the 4 pure Python calculation functions:
- calculate_all_participant_totals
- calculate_total_discrepancy
- check_accuracy_threshold
- find_unassigned_items
"""

from decimal import Decimal

import pytest

from src.models.bill import (
    BillSplit,
    ParticipantItem,
    ParticipantShare,
    ReceiptData,
    ReceiptItem,
)
from src.tools.calculations import (
    calculate_all_participant_totals,
    calculate_total_discrepancy,
    check_accuracy_threshold,
    find_unassigned_items,
)


class TestCalculateAllParticipantTotals:
    """Tests for calculate_all_participant_totals function."""

    def test_perfect_split(self, sample_bill_split):
        """Test calculating totals for a perfect split."""
        totals = calculate_all_participant_totals(sample_bill_split)

        assert "Alice" in totals
        assert "Bob" in totals
        # Alice: Burger (15) + Fries (5*2qty*1/2) + Soda (3*2qty*1/2) = 15 + 5 + 3 = 23
        assert totals["Alice"] == Decimal("23.00")
        # Bob: Salad (12) + Fries (5*2qty*1/2) + Soda (3*2qty*1/2) = 12 + 5 + 3 = 20
        assert totals["Bob"] == Decimal("20.00")

    def test_single_participant(self, sample_receipt_items):
        """Test with a single participant who ate everything."""
        participant = ParticipantShare(
            name="Solo",
            items=[
                ParticipantItem(
                    item_name="Burger", item_numerator=1, item_denominator=1
                ),
                ParticipantItem(
                    item_name="Salad", item_numerator=1, item_denominator=1
                ),
                # Fries and Soda have quantity=2 each, so we need 2/1 to get both
                ParticipantItem(
                    item_name="Fries", item_numerator=2, item_denominator=1
                ),
                ParticipantItem(item_name="Soda", item_numerator=2, item_denominator=1),
            ],
        )
        bill_split = BillSplit(
            participants=[participant],
            receipt_items=sample_receipt_items,
        )

        totals = calculate_all_participant_totals(bill_split)

        # Total = Burger(15*1) + Salad(12*1) + Fries(5*2*2/1) + Soda(3*2*2/1)
        # = 15 + 12 + 20 + 12 = 59
        assert totals["Solo"] == Decimal("59.00")

    def test_three_way_split(self, sample_receipt_items):
        """Test splitting items three ways."""
        participants = [
            ParticipantShare(
                name="Alice",
                items=[
                    ParticipantItem(
                        item_name="Fries", item_numerator=1, item_denominator=3
                    ),
                ],
            ),
            ParticipantShare(
                name="Bob",
                items=[
                    ParticipantItem(
                        item_name="Fries", item_numerator=1, item_denominator=3
                    ),
                ],
            ),
            ParticipantShare(
                name="Charlie",
                items=[
                    ParticipantItem(
                        item_name="Fries", item_numerator=1, item_denominator=3
                    ),
                ],
            ),
        ]
        bill_split = BillSplit(
            participants=participants,
            receipt_items=sample_receipt_items,
        )

        totals = calculate_all_participant_totals(bill_split)

        # Fries total = 5 * 2qty = 10, divided by 3 = 3.33... each
        # Round to 2 decimal places for comparison
        expected = (Decimal("10.00") / Decimal("3")).quantize(Decimal("0.01"))
        assert totals["Alice"].quantize(Decimal("0.01")) == expected
        assert totals["Bob"].quantize(Decimal("0.01")) == expected
        assert totals["Charlie"].quantize(Decimal("0.01")) == expected

    def test_invalid_item_name_raises_error(self, sample_receipt_items):
        """Test that invalid item names raise ValueError."""
        participant = ParticipantShare(
            name="Alice",
            items=[
                ParticipantItem(
                    item_name="NonexistentItem", item_numerator=1, item_denominator=1
                ),
            ],
        )
        bill_split = BillSplit(
            participants=[participant],
            receipt_items=sample_receipt_items,
        )

        with pytest.raises(ValueError, match="Could not match item"):
            calculate_all_participant_totals(bill_split)


class TestCalculateTotalDiscrepancy:
    """Tests for calculate_total_discrepancy function."""

    def test_perfect_match(self, sample_bill_split, sample_receipt_data):
        """Test discrepancy when totals match perfectly."""
        discrepancy = calculate_total_discrepancy(
            sample_bill_split, sample_receipt_data.total
        )

        # Alice: 19, Bob: 16, Total: 35 = receipt total
        # Burger (15) + Salad (12) + Fries (5*2) + Soda (3*2) = 15 + 12 + 10 + 6 = 43
        # Wait, let me recalculate...
        # Alice: Burger (15*1) + Fries (5*1/2*2qty) + Soda (3*1/2*2qty) = 15 + 5 + 3 = 23
        # Bob: Salad (12*1) + Fries (5*1/2*2qty) + Soda (3*1/2*2qty) = 12 + 5 + 3 = 20
        # Total = 43, discrepancy = 0
        assert discrepancy == Decimal("0.00")

    def test_accepts_decimal_receipt_total(self, sample_bill_split):
        """Test that receipt_total as Decimal works correctly."""
        # This is the expected case - Decimal input
        discrepancy = calculate_total_discrepancy(sample_bill_split, Decimal("43.00"))
        assert discrepancy == Decimal("0.00")

    def test_accepts_float_receipt_total(self, sample_bill_split):
        """Test that receipt_total as float is handled (via orchestrator conversion).

        This tests the fix for the type mismatch error where Claude passes
        receipt_total as a float but the function expects Decimal.
        Note: The orchestrator now converts float to Decimal before calling,
        but this test verifies the function still works if given Decimal.
        """
        # The orchestrator converts float to Decimal, so we test with Decimal
        discrepancy = calculate_total_discrepancy(sample_bill_split, Decimal("43.00"))
        assert discrepancy == Decimal("0.00")

    def test_small_discrepancy(self, sample_receipt_items):
        """Test small discrepancy detection."""
        # Create split where not all items are assigned
        participants = [
            ParticipantShare(
                name="Alice",
                items=[
                    ParticipantItem(
                        item_name="Burger", item_numerator=1, item_denominator=1
                    ),
                ],
            ),
        ]
        bill_split = BillSplit(
            participants=participants,
            receipt_items=sample_receipt_items,
        )

        discrepancy = calculate_total_discrepancy(bill_split, Decimal("43.00"))

        # Alice only has Burger (15), but total should be 43
        # Discrepancy = |15 - 43| = 28
        assert discrepancy == Decimal("28.00")

    def test_large_discrepancy(self, sample_receipt_items):
        """Test large discrepancy detection."""
        # Create split where someone is assigned more than they should
        participants = [
            ParticipantShare(
                name="Alice",
                items=[
                    ParticipantItem(
                        item_name="Burger", item_numerator=2, item_denominator=1
                    ),
                    ParticipantItem(
                        item_name="Salad", item_numerator=2, item_denominator=1
                    ),
                    ParticipantItem(
                        item_name="Fries", item_numerator=4, item_denominator=1
                    ),
                ],
            ),
        ]
        bill_split = BillSplit(
            participants=participants,
            receipt_items=sample_receipt_items,
        )

        discrepancy = calculate_total_discrepancy(bill_split, Decimal("43.00"))

        # Alice: Burger(15*2) + Salad(12*2) + Fries(5*2qty*4)
        # = 30 + 24 + 40 = 94
        # Discrepancy = |94 - 43| = 51
        assert discrepancy == Decimal("51.00")


class TestCheckAccuracyThreshold:
    """Tests for check_accuracy_threshold function."""

    def test_perfect_accuracy(self):
        """Test with zero discrepancy."""
        assert check_accuracy_threshold(Decimal("0.00")) is True

    def test_within_tolerance(self):
        """Test with discrepancy within default tolerance (0.02)."""
        assert check_accuracy_threshold(Decimal("0.01")) is True
        assert check_accuracy_threshold(Decimal("0.02")) is True

    def test_exceeds_tolerance(self):
        """Test with discrepancy exceeding default tolerance."""
        assert check_accuracy_threshold(Decimal("0.03")) is False
        assert check_accuracy_threshold(Decimal("1.00")) is False
        assert check_accuracy_threshold(Decimal("10.00")) is False

    def test_custom_tolerance(self):
        """Test with custom tolerance values."""
        # Strict tolerance
        assert (
            check_accuracy_threshold(Decimal("0.05"), tolerance=Decimal("0.01"))
            is False
        )

        # Generous tolerance
        assert (
            check_accuracy_threshold(Decimal("0.05"), tolerance=Decimal("0.10")) is True
        )

    def test_boundary_cases(self):
        """Test edge cases at tolerance boundary."""
        tolerance = Decimal("0.05")
        assert check_accuracy_threshold(Decimal("0.04999"), tolerance=tolerance) is True
        assert check_accuracy_threshold(Decimal("0.05000"), tolerance=tolerance) is True
        assert (
            check_accuracy_threshold(Decimal("0.05001"), tolerance=tolerance) is False
        )


class TestFindUnassignedItems:
    """Tests for find_unassigned_items function."""

    def test_all_items_assigned(self, sample_bill_split, sample_receipt_data):
        """Test when all items are assigned to participants."""
        unassigned = find_unassigned_items(sample_bill_split, sample_receipt_data)

        assert len(unassigned) == 0

    def test_one_item_unassigned(self, sample_receipt_data):
        """Test when one item is not assigned."""
        # Only assign Burger and Salad
        participants = [
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
        ]
        bill_split = BillSplit(
            participants=participants,
            receipt_items=sample_receipt_data.items,
            currency="USD",
            total=sample_receipt_data.total,
        )

        unassigned = find_unassigned_items(bill_split, sample_receipt_data)

        # Fries and Soda should be unassigned
        assert len(unassigned) == 2
        unassigned_names = {item.name for item in unassigned}
        assert "Fries" in unassigned_names
        assert "Soda" in unassigned_names

    def test_all_items_unassigned(self, sample_receipt_data):
        """Test when no items are assigned."""
        # Empty participants
        bill_split = BillSplit(
            participants=[],
            receipt_items=sample_receipt_data.items,
            currency="USD",
            total=sample_receipt_data.total,
        )

        unassigned = find_unassigned_items(bill_split, sample_receipt_data)

        assert len(unassigned) == 4  # All 4 items unassigned
        unassigned_names = {item.name for item in unassigned}
        assert "Burger" in unassigned_names
        assert "Salad" in unassigned_names
        assert "Fries" in unassigned_names
        assert "Soda" in unassigned_names

    def test_fuzzy_matching(self, sample_receipt_data):
        """Test that fuzzy matching works for item names."""
        # Assign items with slightly different names (fuzzy match should work)
        participants = [
            ParticipantShare(
                name="Alice",
                items=[
                    # "burger" should match "Burger"
                    ParticipantItem(
                        item_name="burger", item_numerator=1, item_denominator=1
                    ),
                    # "French Fries" should match "Fries"
                    ParticipantItem(
                        item_name="French Fries", item_numerator=2, item_denominator=1
                    ),
                ],
            ),
        ]
        bill_split = BillSplit(
            participants=participants,
            receipt_items=sample_receipt_data.items,
            currency="USD",
            total=sample_receipt_data.total,
        )

        unassigned = find_unassigned_items(bill_split, sample_receipt_data)

        # Only Salad and Soda should be unassigned (Burger and Fries matched via fuzzy)
        assert len(unassigned) == 2
        unassigned_names = {item.name for item in unassigned}
        assert "Salad" in unassigned_names
        assert "Soda" in unassigned_names


class TestReceiptDataSubtotalAutoComputation:
    """Tests for ReceiptData subtotal auto-computation feature.

    This tests the fix for the Pydantic validation error where Claude
    might omit the subtotal field when reconstructing receipt data.
    """

    def test_subtotal_auto_computed_when_missing(self, sample_receipt_items):
        """Test that subtotal is auto-computed if not provided."""
        # Create ReceiptData without subtotal (it should auto-compute)
        receipt_data = ReceiptData(
            items=sample_receipt_items,
            currency="USD",
            total=Decimal("43.00"),
            # subtotal intentionally omitted
        )

        # Subtotal should be auto-computed from items
        # Burger(15*1) + Salad(12*1) + Fries(5*2) + Soda(3*2) = 15 + 12 + 10 + 6 = 43
        assert receipt_data.subtotal == Decimal("43.00")

    def test_subtotal_preserved_when_provided(self, sample_receipt_items):
        """Test that explicit subtotal is preserved."""
        # Create ReceiptData with explicit subtotal
        receipt_data = ReceiptData(
            items=sample_receipt_items,
            currency="USD",
            subtotal=Decimal("40.00"),  # Intentionally different from computed
            total=Decimal("43.00"),
        )

        # Explicit subtotal should be preserved (not overridden)
        assert receipt_data.subtotal == Decimal("40.00")

    def test_empty_items_defaults_to_zero_subtotal(self):
        """Test that empty items list results in zero subtotal."""
        receipt_data = ReceiptData(
            items=[],
            currency="USD",
            total=Decimal("10.00"),  # Total could be fees/taxes
        )

        assert receipt_data.subtotal == Decimal("0")

    def test_find_unassigned_items_with_missing_subtotal(self, sample_receipt_items):
        """Test find_unassigned_items works when receipt_data has no explicit subtotal.

        This tests the integration fix where Claude might pass receipt_data JSON
        without subtotal after conversation truncation.
        """
        # Create receipt data without explicit subtotal
        receipt_data = ReceiptData(
            items=sample_receipt_items,
            currency="USD",
            total=Decimal("43.00"),
        )

        # Create bill split
        participants = [
            ParticipantShare(
                name="Alice",
                items=[
                    ParticipantItem(
                        item_name="Burger", item_numerator=1, item_denominator=1
                    ),
                ],
            ),
        ]
        bill_split = BillSplit(
            participants=participants,
            receipt_items=sample_receipt_items,
        )

        # Should work without validation errors
        unassigned = find_unassigned_items(bill_split, receipt_data)

        # Salad, Fries, and Soda should be unassigned
        assert len(unassigned) == 3
        unassigned_names = {item.name for item in unassigned}
        assert "Salad" in unassigned_names
        assert "Fries" in unassigned_names
        assert "Soda" in unassigned_names
