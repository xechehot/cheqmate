"""Utility functions for bill calculations and validation."""

import logging
from decimal import Decimal

from src.models.bill import (
    BillSplit,
    ParticipantItem,
    ParticipantShare,
    ReceiptItem,
    SplitDiscrepancy,
    format_currency,
)

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


def find_receipt_item_by_name(
    item_name: str, receipt_items: list[ReceiptItem]
) -> ReceiptItem | None:
    """
    Find a single receipt item by name using fuzzy matching.

    Args:
        item_name: Name of the item to find
        receipt_items: All items from the receipt

    Returns:
        Matched ReceiptItem or None if not found
    """
    item_name_lower = item_name.lower().strip()

    # Try exact match first (case-insensitive)
    for receipt_item in receipt_items:
        if receipt_item.description.lower().strip() == item_name_lower:
            return receipt_item

    # Try partial match (fuzzy)
    for receipt_item in receipt_items:
        if (
            item_name_lower in receipt_item.description.lower()
            or receipt_item.description.lower() in item_name_lower
        ):
            return receipt_item

    return None


def calculate_participant_item_total(
    participant_item: ParticipantItem, receipt_items: list[ReceiptItem]
) -> Decimal:
    """
    Calculate the total cost for a single participant item.

    Formula: (line_nominator / line_denominator) × receipt_item.line_total

    Args:
        participant_item: The participant's item with fractional quantity
        receipt_items: All items from the receipt

    Returns:
        Total cost for this item (Decimal)
    """
    # Find matching receipt item
    receipt_item = find_receipt_item_by_name(participant_item.item_name, receipt_items)

    if receipt_item is None:
        logger.warning(
            f"Could not find receipt item matching '{participant_item.item_name}'"
        )
        return Decimal("0")

    # Calculate fractional share
    fraction = Decimal(participant_item.line_nominator) / Decimal(
        participant_item.line_denominator
    )
    item_total = fraction * receipt_item.line_total

    logger.debug(
        f"Item '{participant_item.item_name}': "
        f"{participant_item.line_nominator}/{participant_item.line_denominator} "
        f"× {receipt_item.line_total} = {item_total}"
    )

    return item_total


def calculate_participant_total(
    participant_items: list[ParticipantItem], receipt_items: list[ReceiptItem]
) -> Decimal:
    """
    Calculate total amount for a participant based on their items.

    Args:
        participant_items: List of ParticipantItem objects
        receipt_items: All items from the receipt

    Returns:
        Total amount this participant owes (Decimal)
    """
    total = Decimal("0")
    for item in participant_items:
        item_total = calculate_participant_item_total(item, receipt_items)
        total += item_total

    return total


def calculate_split_discrepancy(
    bill_split: BillSplit,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Calculate discrepancy between sum of participant totals and receipt total.

    Args:
        bill_split: The complete bill split

    Returns:
        Tuple of (calculated_split_total, discrepancy_amount, discrepancy_percentage)
    """
    # Calculate total from all participants
    calculated_split_total = Decimal("0")
    for participant in bill_split.participants:
        participant_total = calculate_participant_total(
            participant.items, bill_split.receipt.items
        )
        calculated_split_total += participant_total

    # Calculate discrepancy
    discrepancy_amount, discrepancy_pct = calculate_discrepancy(
        bill_split.receipt.total, calculated_split_total
    )

    return calculated_split_total, discrepancy_amount, discrepancy_pct


def validate_split(
    bill_split: BillSplit, threshold_percentage: Decimal = Decimal("1.0")
) -> tuple[bool, str, dict[str, Decimal]]:
    """
    Validate that the bill split amounts are mathematically correct.

    This function:
    1. Calculates participant totals from their ParticipantItem objects
    2. Sums all participant totals
    3. Calculates discrepancy from original receipt total
    4. Returns validation result

    Args:
        bill_split: The complete bill split to validate
        threshold_percentage: Acceptable discrepancy as percentage (default: 1.0%)

    Returns:
        Tuple of:
        - is_valid: True if discrepancy is within threshold
        - message: Human-readable validation message
        - details: Dict with calculated_total, discrepancy_amount, discrepancy_pct
    """
    receipt = bill_split.receipt

    # Calculate split total using new ParticipantItem-based calculation
    calculated_split_total, discrepancy_amount, discrepancy_pct = (
        calculate_split_discrepancy(bill_split)
    )

    # Prepare details dict
    details = {
        "calculated_total": calculated_split_total,
        "original_total": receipt.total,
        "discrepancy_amount": discrepancy_amount,
        "discrepancy_pct": discrepancy_pct,
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
        f"discrepancy={discrepancy_amount} ({discrepancy_pct:.2f}%), valid={is_valid}"
    )

    return is_valid, message, details


def analyze_split_discrepancy(bill_split: BillSplit) -> SplitDiscrepancy:
    """
    Analyze discrepancies between the receipt and bill split.

    This function:
    1. Identifies receipt items not assigned to any participant
    2. Calculates total discrepancy between receipt and split
    3. Returns structured analysis for LLM refinement

    Args:
        bill_split: The complete bill split to analyze

    Returns:
        SplitDiscrepancy object with detailed analysis
    """
    # Calculate split totals and discrepancy
    calculated_split_total, discrepancy_amount, discrepancy_pct = (
        calculate_split_discrepancy(bill_split)
    )

    # Find missed items: receipt items not assigned to any participant
    assigned_item_names = set()
    for participant in bill_split.participants:
        for item in participant.items:
            # Normalize for comparison (case-insensitive, stripped)
            assigned_item_names.add(item.item_name.lower().strip())

    missed_items = []
    for receipt_item in bill_split.receipt.items:
        receipt_item_name = receipt_item.description.lower().strip()
        # Check if this receipt item appears in any participant's items
        if receipt_item_name not in assigned_item_names:
            # Also try fuzzy matching to account for slight name variations
            found = False
            for assigned_name in assigned_item_names:
                if (
                    assigned_name in receipt_item_name
                    or receipt_item_name in assigned_name
                ):
                    found = True
                    break
            if not found:
                missed_items.append(receipt_item)

    logger.info(
        f"Discrepancy analysis: split_total={calculated_split_total}, "
        f"original_total={bill_split.receipt.total}, "
        f"difference={discrepancy_amount} ({discrepancy_pct:.2f}%), "
        f"missed_items={len(missed_items)}"
    )

    return SplitDiscrepancy(
        original_total=bill_split.receipt.total,
        split_total=calculated_split_total,
        total_difference=bill_split.receipt.total - calculated_split_total,
        percentage_difference=discrepancy_pct,
        missed_items=missed_items,
    )
