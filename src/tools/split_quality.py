"""Consolidated split quality evaluation tool.

This module provides a single comprehensive evaluation function that replaces
4 separate calculation tools, reducing agent iterations and providing holistic
quality metrics in one call.

Replaces:
- calculate_all_participant_totals
- calculate_total_discrepancy
- check_accuracy_threshold
- find_unassigned_items
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from src.models.bill import BillSplit, ReceiptData, ReceiptItem

logger = logging.getLogger(__name__)


@dataclass
class SplitQualityMetrics:
    """Comprehensive quality metrics for a bill split."""

    # Participant totals
    participant_totals: dict[str, Decimal]
    participants_sum: Decimal
    participant_count: int

    # Receipt comparison
    receipt_total: Decimal
    total_discrepancy: Decimal

    # Unassigned items
    unassigned_items: list[ReceiptItem]
    unassigned_count: int

    # Quality assessment
    passes_accuracy_threshold: bool
    is_complete: bool  # All items assigned AND discrepancy acceptable

    def to_dict(self) -> dict:
        """
        Convert metrics to dictionary for JSON serialization.

        Returns:
            Dictionary with all metrics, Decimal values converted to float
        """
        return {
            "participant_totals": {
                name: float(total) for name, total in self.participant_totals.items()
            },
            "participants_sum": float(self.participants_sum),
            "participant_count": self.participant_count,
            "receipt_total": float(self.receipt_total),
            "total_discrepancy": float(self.total_discrepancy),
            "unassigned_items": [
                {
                    "name": item.name,
                    "price": float(item.price),
                    "quantity": item.quantity,
                    "total_price": float(item.total_price),
                }
                for item in self.unassigned_items
            ],
            "unassigned_count": self.unassigned_count,
            "passes_accuracy_threshold": self.passes_accuracy_threshold,
            "is_complete": self.is_complete,
        }

    def format_summary(self) -> str:
        """
        Format metrics as human-readable summary.

        Returns:
            Formatted summary string
        """
        lines = ["**Split Quality Metrics:**", ""]

        # Participant totals
        lines.append("**Participant Totals:**")
        for name, total in self.participant_totals.items():
            lines.append(f"  • {name}: {total}")
        lines.append(f"  **Sum**: {self.participants_sum}")
        lines.append("")

        # Comparison
        lines.append(f"**Receipt Total**: {self.receipt_total}")
        lines.append(f"**Discrepancy**: {self.total_discrepancy}")
        lines.append(
            f"**Accuracy**: {'✅ PASS' if self.passes_accuracy_threshold else '❌ FAIL'} (threshold: 0.02)"
        )
        lines.append("")

        # Unassigned items
        if self.unassigned_count > 0:
            lines.append(f"**Unassigned Items**: {self.unassigned_count}")
            for item in self.unassigned_items:
                lines.append(f"  • {item.name}: {item.total_price}")
        else:
            lines.append("**Unassigned Items**: ✅ None")
        lines.append("")

        # Overall
        lines.append(
            f"**Overall**: {'✅ COMPLETE' if self.is_complete else '❌ INCOMPLETE'}"
        )

        return "\n".join(lines)


def evaluate_split_quality(
    bill_split: BillSplit,
    receipt_data: ReceiptData,
    tolerance: Decimal = Decimal("0.02"),
) -> SplitQualityMetrics:
    """
    Evaluate the quality of a bill split with comprehensive metrics.

    This function consolidates 4 separate calculation tools into one:
    1. calculate_all_participant_totals → participant_totals
    2. calculate_total_discrepancy → total_discrepancy
    3. check_accuracy_threshold → passes_accuracy_threshold
    4. find_unassigned_items → unassigned_items

    Args:
        bill_split: Complete bill split with participant assignments
        receipt_data: Original receipt data for comparison
        tolerance: Maximum acceptable discrepancy (default: 0.02)

    Returns:
        SplitQualityMetrics with all quality metrics

    Raises:
        ValueError: If item matching fails during calculation
    """
    logger.debug("Evaluating split quality")

    # 1. Calculate participant totals
    participant_totals: dict[str, Decimal] = {}
    for participant in bill_split.participants:
        try:
            calculated_total = participant.calculate_total(bill_split.receipt_items)
            participant_totals[participant.name] = calculated_total
            logger.debug(f"Calculated total for {participant.name}: {calculated_total}")
        except ValueError as e:
            logger.error(f"Calculation error for {participant.name}: {e}")
            raise

    participants_sum = sum(participant_totals.values())
    participant_count = len(bill_split.participants)

    # 2. Calculate discrepancy
    receipt_total = receipt_data.total
    total_discrepancy = abs(participants_sum - receipt_total)
    logger.debug(
        f"Discrepancy: participants_sum={participants_sum}, "
        f"receipt_total={receipt_total}, diff={total_discrepancy}"
    )

    # 3. Check accuracy threshold
    passes_accuracy = total_discrepancy <= tolerance
    logger.debug(
        f"Accuracy check: discrepancy={total_discrepancy}, "
        f"tolerance={tolerance}, passes={passes_accuracy}"
    )

    # 4. Find unassigned items
    unassigned_items = _find_unassigned_items(bill_split, receipt_data)
    unassigned_count = len(unassigned_items)

    if unassigned_count > 0:
        logger.info(f"Found {unassigned_count} unassigned items")
        for item in unassigned_items:
            logger.debug(f"  Unassigned: {item.name}")
    else:
        logger.debug("All receipt items are assigned")

    # 5. Overall assessment
    is_complete = passes_accuracy and unassigned_count == 0

    metrics = SplitQualityMetrics(
        participant_totals=participant_totals,
        participants_sum=participants_sum,
        participant_count=participant_count,
        receipt_total=receipt_total,
        total_discrepancy=total_discrepancy,
        unassigned_items=unassigned_items,
        unassigned_count=unassigned_count,
        passes_accuracy_threshold=passes_accuracy,
        is_complete=is_complete,
    )

    logger.info(
        f"Split quality: {'COMPLETE' if is_complete else 'INCOMPLETE'} "
        f"(discrepancy={total_discrepancy}, unassigned={unassigned_count})"
    )

    return metrics


def _find_unassigned_items(
    bill_split: BillSplit, receipt_data: ReceiptData
) -> list[ReceiptItem]:
    """
    Find receipt items that are not assigned to any participant.

    Helper function extracted from find_unassigned_items in calculations.py.

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

    return unassigned
