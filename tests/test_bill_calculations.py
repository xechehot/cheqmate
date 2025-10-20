"""Tests for bill calculation utilities."""

from decimal import Decimal


from src.models.bill import (
    BillSplit,
    ParticipantItem,
    ParticipantShare,
    Receipt,
    ReceiptItem,
    format_currency,
)
from src.utils.bill_calculations import (
    calculate_discrepancy,
    calculate_person_subtotal,
    calculate_split_total,
    find_receipt_items_by_description,
    validate_split,
)


class TestFormatCurrency:
    """Test suite for currency formatting."""

    def test_format_usd(self):
        """Test USD currency formatting."""
        assert format_currency(Decimal("100.50"), "USD") == "$100.50"
        assert format_currency(Decimal("0.99"), "USD") == "$0.99"
        assert format_currency(Decimal("1000"), "USD") == "$1000.00"

    def test_format_eur(self):
        """Test EUR currency formatting."""
        assert format_currency(Decimal("100.50"), "EUR") == "100.50 €"
        assert format_currency(Decimal("0.99"), "EUR") == "0.99 €"

    def test_format_kzt(self):
        """Test KZT currency formatting."""
        assert format_currency(Decimal("8400"), "KZT") == "8400.00 ₸"
        assert format_currency(Decimal("100.50"), "KZT") == "100.50 ₸"

    def test_format_gbp(self):
        """Test GBP currency formatting."""
        assert format_currency(Decimal("100.50"), "GBP") == "£100.50"

    def test_format_jpy(self):
        """Test JPY currency formatting."""
        assert format_currency(Decimal("1000"), "JPY") == "¥1000.00"

    def test_format_rub(self):
        """Test RUB currency formatting."""
        assert format_currency(Decimal("100.50"), "RUB") == "100.50 ₽"

    def test_format_unknown_currency(self):
        """Test unknown currency code falls back to code display."""
        assert format_currency(Decimal("100.50"), "XYZ") == "100.50 XYZ"

    def test_format_lowercase_currency(self):
        """Test currency codes are case-insensitive."""
        assert format_currency(Decimal("100.50"), "usd") == "$100.50"
        assert format_currency(Decimal("100.50"), "eur") == "100.50 €"


class TestFindReceiptItems:
    """Test suite for finding receipt items by description."""

    def test_exact_match(self, sample_receipt_usd: Receipt):
        """Test exact match (case-insensitive)."""
        items = find_receipt_items_by_description(["Burger"], sample_receipt_usd.items)
        assert len(items) == 1
        assert items[0].description == "Burger"

    def test_exact_match_case_insensitive(self, sample_receipt_usd: Receipt):
        """Test exact match is case-insensitive."""
        items = find_receipt_items_by_description(["burger"], sample_receipt_usd.items)
        assert len(items) == 1
        assert items[0].description == "Burger"

    def test_multiple_items(self, sample_receipt_usd: Receipt):
        """Test finding multiple items."""
        items = find_receipt_items_by_description(
            ["Burger", "Salad"], sample_receipt_usd.items
        )
        assert len(items) == 2
        assert items[0].description == "Burger"
        assert items[1].description == "Salad"

    def test_fuzzy_match_partial(self, sample_receipt_usd: Receipt):
        """Test fuzzy matching with partial text."""
        items = find_receipt_items_by_description(["Burg"], sample_receipt_usd.items)
        assert len(items) == 1
        assert items[0].description == "Burger"

    def test_no_match(self, sample_receipt_usd: Receipt):
        """Test no match returns empty list."""
        items = find_receipt_items_by_description(["Pizza"], sample_receipt_usd.items)
        assert len(items) == 0

    def test_whitespace_handling(self, sample_receipt_usd: Receipt):
        """Test whitespace is stripped."""
        items = find_receipt_items_by_description(
            ["  Burger  "], sample_receipt_usd.items
        )
        assert len(items) == 1
        assert items[0].description == "Burger"


class TestCalculatePersonSubtotal:
    """Test suite for calculating person's subtotal."""

    def test_single_item(self, sample_receipt_usd: Receipt):
        """Test calculating subtotal for single item."""
        subtotal = calculate_person_subtotal(["Burger"], sample_receipt_usd.items)
        assert subtotal == Decimal("15.00")

    def test_multiple_items(self, sample_receipt_usd: Receipt):
        """Test calculating subtotal for multiple items."""
        subtotal = calculate_person_subtotal(
            ["Burger", "Salad"], sample_receipt_usd.items
        )
        assert subtotal == Decimal("27.00")  # 15 + 12

    def test_all_items(self, sample_receipt_usd: Receipt):
        """Test calculating subtotal for all items."""
        subtotal = calculate_person_subtotal(
            ["Burger", "Salad", "Pasta"], sample_receipt_usd.items
        )
        assert subtotal == Decimal("45.00")

    def test_no_items(self, sample_receipt_usd: Receipt):
        """Test calculating subtotal with no items."""
        subtotal = calculate_person_subtotal([], sample_receipt_usd.items)
        assert subtotal == Decimal("0")

    def test_nonexistent_item(self, sample_receipt_usd: Receipt):
        """Test calculating subtotal with nonexistent item."""
        subtotal = calculate_person_subtotal(["Pizza"], sample_receipt_usd.items)
        assert subtotal == Decimal("0")


class TestCalculateSplitTotal:
    """Test suite for calculating split total (deprecated function - kept for backward compatibility)."""

    def test_no_participants(self, sample_receipt_usd: Receipt):
        """Test calculating total with no participants."""
        total = calculate_split_total([], sample_receipt_usd.items)
        assert total == Decimal("0")


class TestCalculateDiscrepancy:
    """Test suite for calculating discrepancy."""

    def test_no_discrepancy(self):
        """Test when totals match exactly."""
        diff, pct = calculate_discrepancy(Decimal("100"), Decimal("100"))
        assert diff == Decimal("0")
        assert pct == Decimal("0")

    def test_positive_discrepancy(self):
        """Test when split total is higher."""
        diff, pct = calculate_discrepancy(Decimal("100"), Decimal("110"))
        assert diff == Decimal("10")
        assert pct == Decimal("10")

    def test_negative_discrepancy(self):
        """Test when split total is lower."""
        diff, pct = calculate_discrepancy(Decimal("100"), Decimal("90"))
        assert diff == Decimal("10")
        assert pct == Decimal("10")

    def test_small_discrepancy(self):
        """Test small rounding discrepancy."""
        diff, pct = calculate_discrepancy(Decimal("100"), Decimal("100.50"))
        assert diff == Decimal("0.50")
        assert pct == Decimal("0.5")

    def test_zero_total(self):
        """Test with zero original total."""
        diff, pct = calculate_discrepancy(Decimal("0"), Decimal("10"))
        assert diff == Decimal("10")
        assert pct == Decimal("0")


class TestValidateSplit:
    """Test suite for bill split validation."""

    def test_perfect_split(self, sample_bill_split_usd: BillSplit):
        """Test validation of a perfect split (no discrepancy)."""
        is_valid, message, details = validate_split(sample_bill_split_usd)

        assert is_valid is True
        assert "✅" in message
        assert "mathematically correct" in message
        assert details["discrepancy_amount"] == Decimal("0")
        assert details["discrepancy_pct"] == Decimal("0")
        assert details["calculated_total"] == Decimal("45.00")
        assert details["original_total"] == Decimal("45.00")

    def test_acceptable_discrepancy(self):
        """Test validation with small acceptable discrepancy (<1%)."""
        receipt = Receipt(
            restaurant_name="Test",
            currency="USD",
            items=[
                ReceiptItem(description="Item", line_total=Decimal("100.00")),
            ],
            total=Decimal("100.50"),  # 0.5% discrepancy
        )
        participants = [
            ParticipantShare(
                name="Alice",
                items=[
                    ParticipantItem(
                        item_name="Item", line_nominator=1, line_denominator=1
                    )
                ],
                amount=Decimal("100.00"),
            ),
        ]
        bill_split = BillSplit(participants=participants, receipt=receipt)

        is_valid, message, details = validate_split(bill_split)

        assert is_valid is True
        assert "✅" in message
        assert "within acceptable range" in message
        assert details["discrepancy_amount"] == Decimal("0.50")
        assert details["discrepancy_pct"] < Decimal("1.0")

    def test_unacceptable_discrepancy(self):
        """Test validation with large discrepancy (>1%)."""
        receipt = Receipt(
            restaurant_name="Test",
            currency="USD",
            items=[
                ReceiptItem(description="Item1", line_total=Decimal("50.00")),
                ReceiptItem(description="Item2", line_total=Decimal("50.00")),
            ],
            total=Decimal("100.00"),
        )
        # Only assigned one item (missing 50%)
        participants = [
            ParticipantShare(
                name="Alice",
                items=[
                    ParticipantItem(
                        item_name="Item1", line_nominator=1, line_denominator=1
                    )
                ],
                amount=Decimal("50.00"),
            ),
        ]
        bill_split = BillSplit(participants=participants, receipt=receipt)

        is_valid, message, details = validate_split(bill_split)

        assert is_valid is False
        assert "⚠️" in message
        assert "Warning" in message
        assert details["discrepancy_amount"] == Decimal("50.00")
        assert details["discrepancy_pct"] == Decimal("50")

    def test_validation_with_kzt_currency(self, sample_receipt_kzt: Receipt):
        """Test validation works with different currency."""
        participants = [
            ParticipantShare(
                name="Alice",
                items=[
                    ParticipantItem(
                        item_name="Beshbarmak", line_nominator=1, line_denominator=1
                    )
                ],
                amount=Decimal("3500"),
            ),
            ParticipantShare(
                name="Bob",
                items=[
                    ParticipantItem(
                        item_name="Lagman", line_nominator=1, line_denominator=1
                    ),
                    ParticipantItem(
                        item_name="Tea", line_nominator=1, line_denominator=1
                    ),
                ],
                amount=Decimal("4900"),
            ),
        ]
        bill_split = BillSplit(participants=participants, receipt=sample_receipt_kzt)

        is_valid, message, details = validate_split(bill_split)

        assert is_valid is True
        assert details["calculated_total"] == Decimal("8400")
        assert details["original_total"] == Decimal("8400")
        # When split is perfect, validation message is simple and doesn't show currency
        assert "✅" in message

    def test_missing_items_warning(self):
        """Test that missing items trigger validation warning."""
        receipt = Receipt(
            restaurant_name="Test",
            currency="USD",
            items=[
                ReceiptItem(description="Item1", line_total=Decimal("30.00")),
                ReceiptItem(description="Item2", line_total=Decimal("30.00")),
                ReceiptItem(description="Item3", line_total=Decimal("30.00")),
            ],
            total=Decimal("90.00"),
        )
        # Only assigned 2 of 3 items
        participants = [
            ParticipantShare(
                name="Alice",
                items=[
                    ParticipantItem(
                        item_name="Item1", line_nominator=1, line_denominator=1
                    )
                ],
                amount=Decimal("30.00"),
            ),
            ParticipantShare(
                name="Bob",
                items=[
                    ParticipantItem(
                        item_name="Item2", line_nominator=1, line_denominator=1
                    )
                ],
                amount=Decimal("30.00"),
            ),
        ]
        bill_split = BillSplit(participants=participants, receipt=receipt)

        is_valid, message, details = validate_split(bill_split)

        assert is_valid is False
        assert "Some items weren't assigned" in message
        assert details["discrepancy_pct"] > Decimal("30")  # ~33%

    def test_custom_threshold(self):
        """Test validation with custom threshold."""
        receipt = Receipt(
            restaurant_name="Test",
            currency="USD",
            items=[
                ReceiptItem(description="Item", line_total=Decimal("100.00")),
            ],
            total=Decimal("102.00"),  # 2% discrepancy
        )
        participants = [
            ParticipantShare(
                name="Alice",
                items=[
                    ParticipantItem(
                        item_name="Item", line_nominator=1, line_denominator=1
                    )
                ],
                amount=Decimal("100.00"),
            ),
        ]
        bill_split = BillSplit(participants=participants, receipt=receipt)

        # Should fail with 1% threshold
        is_valid, _, _ = validate_split(bill_split, threshold_percentage=Decimal("1.0"))
        assert is_valid is False

        # Should pass with 5% threshold
        is_valid, _, _ = validate_split(bill_split, threshold_percentage=Decimal("5.0"))
        assert is_valid is True
