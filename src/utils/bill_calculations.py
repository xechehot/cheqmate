"""Utility functions for bill calculations and validation."""

import logging
from decimal import Decimal

from src.models.bill import BillSplit, ParticipantShare, ReceiptItem, format_currency

logger = logging.getLogger(__name__)


def find_receipt_items_by_description(
    item_descriptions: list[str], receipt_items: list[ReceiptItem]
) -> list[ReceiptItem]:
    """
    Find receipt items that match the given descriptions (case-insensitive, fuzzy).

    Args:
        item_descriptions: List of item names/descriptions to find
        receipt_items: All items from the original receipt

    Returns:
        List of matched ReceiptItem objects
    """
    matched_items = []

    for desc in item_descriptions:
        # Try exact match first (case-insensitive)
        desc_lower = desc.lower().strip()
        for receipt_item in receipt_items:
            if receipt_item.description.lower().strip() == desc_lower:
                matched_items.append(receipt_item)
                break
        else:
            # Try partial match (fuzzy)
            for receipt_item in receipt_items:
                if (
                    desc_lower in receipt_item.description.lower()
                    or receipt_item.description.lower() in desc_lower
                ):
                    matched_items.append(receipt_item)
                    break

    return matched_items


def calculate_person_subtotal(
    person_items: list[str], receipt_items: list[ReceiptItem]
) -> Decimal:
    """
    Calculate a person's subtotal by summing their items from the receipt.

    This uses the actual receipt data (line_total) instead of relying on LLM arithmetic.

    Args:
        person_items: List of item descriptions assigned to this person
        receipt_items: All items from the original receipt

    Returns:
        Accurate subtotal calculated from receipt data
    """
    matched_items = find_receipt_items_by_description(person_items, receipt_items)

    subtotal = Decimal("0")
    for item in matched_items:
        subtotal += item.line_total

    return subtotal


def calculate_split_total(
    participants: list[ParticipantShare], receipt_items: list[ReceiptItem]
) -> Decimal:
    """
    Calculate the total of the split by summing all participants' subtotals.

    Uses actual receipt data for accurate calculation.

    Args:
        participants: List of all participants with their assigned items
        receipt_items: All items from the original receipt

    Returns:
        Total amount calculated from summing all participants
    """
    total = Decimal("0")
    for participant in participants:
        person_subtotal = calculate_person_subtotal(participant.items, receipt_items)
        total += person_subtotal

    return total


def calculate_discrepancy(
    original_total: Decimal, split_total: Decimal
) -> tuple[Decimal, Decimal]:
    """
    Calculate the discrepancy between the original total and the split total.

    Args:
        original_total: Total from the receipt
        split_total: Sum of all participants' amounts

    Returns:
        Tuple of (absolute_difference, percentage_difference)
        - absolute_difference: The raw difference in currency units
        - percentage_difference: The percentage difference relative to original total
    """
    absolute_diff = abs(original_total - split_total)

    # Calculate percentage (avoid division by zero)
    if original_total > 0:
        percentage_diff = (absolute_diff / original_total) * Decimal("100")
    else:
        percentage_diff = Decimal("0")

    return absolute_diff, percentage_diff


def validate_split(
    bill_split: BillSplit, threshold_percentage: Decimal = Decimal("1.0")
) -> tuple[bool, str, dict[str, Decimal]]:
    """
    Validate that the bill split amounts are mathematically correct.

    This function:
    1. Calculates accurate subtotals using Python (not LLM math)
    2. Compares with LLM-provided amounts
    3. Calculates discrepancy from original total
    4. Returns validation result

    Args:
        bill_split: The complete bill split to validate
        threshold_percentage: Acceptable discrepancy as percentage (default: 1.0%)

    Returns:
        Tuple of:
        - is_valid: True if discrepancy is within threshold
        - message: Human-readable validation message
        - details: Dict with calculated_total, llm_total, discrepancy_amount, discrepancy_pct
    """
    receipt = bill_split.receipt
    participants = bill_split.participants

    # Calculate accurate split total using Python and receipt data
    calculated_split_total = calculate_split_total(participants, receipt.items)

    # Sum up LLM-provided amounts
    llm_split_total = sum(
        (participant.amount for participant in participants), start=Decimal("0")
    )

    # Calculate discrepancy from original receipt total
    discrepancy_amount, discrepancy_pct = calculate_discrepancy(
        receipt.total, calculated_split_total
    )

    # Calculate discrepancy between LLM amounts and calculated amounts
    llm_diff, llm_diff_pct = calculate_discrepancy(
        llm_split_total, calculated_split_total
    )

    # Prepare details dict
    details = {
        "calculated_total": calculated_split_total,
        "llm_total": llm_split_total,
        "original_total": receipt.total,
        "discrepancy_amount": discrepancy_amount,
        "discrepancy_pct": discrepancy_pct,
        "llm_diff_amount": llm_diff,
        "llm_diff_pct": llm_diff_pct,
    }

    # Check if within threshold
    is_valid = discrepancy_pct <= threshold_percentage

    # Format currency for message
    currency = receipt.currency
    calculated_fmt = format_currency(calculated_split_total, currency)
    original_fmt = format_currency(receipt.total, currency)
    discrepancy_fmt = format_currency(discrepancy_amount, currency)

    if is_valid:
        if discrepancy_amount == 0:
            message = "✅ Split is mathematically correct!"
        else:
            message = f"✅ Split is within acceptable range (discrepancy: {discrepancy_fmt}, {discrepancy_pct:.2f}%)"
    else:
        message = (
            f"⚠️ **Split Validation Warning**\n\n"
            f"The calculated split total ({calculated_fmt}) differs from the receipt total ({original_fmt}) "
            f"by {discrepancy_fmt} ({discrepancy_pct:.2f}%).\n\n"
            f"This may indicate:\n"
            f"• Some items weren't assigned to anyone\n"
            f"• Some items were assigned to multiple people\n"
            f"• Shared items may need manual adjustment"
        )

    logger.info(
        f"Split validation: original={receipt.total}, calculated={calculated_split_total}, "
        f"llm={llm_split_total}, discrepancy={discrepancy_amount} ({discrepancy_pct:.2f}%), "
        f"valid={is_valid}"
    )

    return is_valid, message, details
