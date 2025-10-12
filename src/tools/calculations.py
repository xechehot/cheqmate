"""Pure Python calculation tools for bill splitting.

These tools perform deterministic mathematical operations without any LLM calls.
All calculations are based on fractional ownership model.
"""

import logging
from decimal import Decimal

from src.models.bill import BillSplit, ReceiptData, ReceiptItem

logger = logging.getLogger(__name__)


def calculate_all_participant_totals(bill_split: BillSplit) -> dict[str, Decimal]:
    """
    Calculate the total amount each participant owes.

    Args:
        bill_split: Complete bill split with participant assignments

    Returns:
        Dictionary mapping participant name to their total amount

    Raises:
        ValueError: If item matching fails for any participant
    """
    participant_totals: dict[str, Decimal] = {}

    for participant in bill_split.participants:
        try:
            calculated_total = participant.calculate_total(bill_split.receipt_items)
            participant_totals[participant.name] = calculated_total
            logger.debug(
                f"Calculated total for {participant.name}: {calculated_total}"
            )
        except ValueError as e:
            logger.error(f"Calculation error for {participant.name}: {e}")
            raise

    return participant_totals


def calculate_total_discrepancy(
    bill_split: BillSplit, receipt_total: Decimal
) -> Decimal:
    """
    Calculate the difference between sum of participant totals and receipt total.

    Args:
        bill_split: Complete bill split with participant assignments
        receipt_total: Target total from receipt

    Returns:
        Absolute difference between calculated sum and target total

    Raises:
        ValueError: If item matching fails during calculation
    """
    participant_totals = calculate_all_participant_totals(bill_split)
    participants_sum = sum(participant_totals.values())
    discrepancy = abs(participants_sum - receipt_total)

    logger.debug(
        f"Calculated discrepancy: participants_sum={participants_sum}, "
        f"receipt_total={receipt_total}, diff={discrepancy}"
    )

    return discrepancy


def check_accuracy_threshold(
    discrepancy: Decimal, tolerance: Decimal = Decimal("0.02")
) -> bool:
    """
    Check if the split is accurate within tolerance.

    Args:
        discrepancy: Absolute difference between calculated sum and target
        tolerance: Maximum acceptable difference (default: 0.02)

    Returns:
        True if split is accurate (discrepancy <= tolerance), False otherwise
    """
    is_accurate = discrepancy <= tolerance
    logger.debug(
        f"Accuracy check: discrepancy={discrepancy}, "
        f"tolerance={tolerance}, accurate={is_accurate}"
    )
    return is_accurate


def find_unassigned_items(
    bill_split: BillSplit, receipt_data: ReceiptData
) -> list[ReceiptItem]:
    """
    Find receipt items that are not assigned to any participant.

    This checks if each receipt item appears in at least one participant's
    item list (using fuzzy matching).

    Args:
        bill_split: Complete bill split with participant assignments
        receipt_data: Original receipt data

    Returns:
        List of receipt items that are not assigned to anyone
    """
    from src.models.bill import find_receipt_item

    unassigned: list[ReceiptItem] = []

    # Collect all item names that are assigned to participants
    assigned_item_names: set[str] = set()
    for participant in bill_split.participants:
        for participant_item in participant.items:
            assigned_item_names.add(participant_item.item_name.lower())

    # Check each receipt item to see if it's assigned
    for receipt_item in receipt_data.items:
        # Try to match this receipt item to any assigned item name
        is_assigned = False
        for assigned_name in assigned_item_names:
            # Use the same fuzzy matching logic
            matched = find_receipt_item(assigned_name, [receipt_item], threshold=80)
            if matched:
                is_assigned = True
                break

        if not is_assigned:
            unassigned.append(receipt_item)
            logger.debug(f"Found unassigned item: {receipt_item.name}")

    if unassigned:
        logger.info(f"Found {len(unassigned)} unassigned items")
    else:
        logger.debug("All receipt items are assigned")

    return unassigned
