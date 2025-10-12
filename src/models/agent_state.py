"""Extended conversation state for agent orchestration.

This module extends the base BillSession with agent-specific state storage,
including caching of intermediate results to avoid redundant expensive operations.
"""

import logging

from src.models.bill import BillSplit, ReceiptData
from src.models.conversation_state import BillSession

logger = logging.getLogger(__name__)


class AgentBillSession(BillSession):
    """Extended session with agent-specific state storage and result caching."""

    def __init__(self) -> None:
        """Initialize extended session with agent state."""
        super().__init__()

        # Intermediate results cached during processing
        # These avoid redundant expensive operations (OCR, split creation)
        self.receipt_data: ReceiptData | None = None
        self.bill_split: BillSplit | None = None
        self.image_bytes: bytes | None = None  # Cache downloaded receipt image

        # Agent execution tracking (for debugging/observability)
        self.agent_turns: int = 0
        self.last_error: str | None = None

    def reset(self) -> None:
        """Reset session including agent-specific state."""
        super().reset()
        self.receipt_data = None
        self.bill_split = None
        self.image_bytes = None
        self.agent_turns = 0
        self.last_error = None
        logger.debug("Agent session reset")

    def store_receipt_data(self, receipt_data: ReceiptData) -> None:
        """
        Store receipt OCR results in session for reuse.

        Args:
            receipt_data: Extracted receipt data from OCR
        """
        self.receipt_data = receipt_data
        logger.info(
            f"Stored receipt data: {len(receipt_data.items)} items, "
            f"total: {receipt_data.total} {receipt_data.currency}"
        )

    def store_bill_split(self, bill_split: BillSplit) -> None:
        """
        Store bill split results in session for reuse.

        Args:
            bill_split: Complete bill split with participant assignments
        """
        self.bill_split = bill_split
        logger.info(f"Stored bill split: {len(bill_split.participants)} participants")

    def increment_turn(self) -> None:
        """Increment agent turn counter for tracking."""
        self.agent_turns += 1
        logger.debug(f"Agent turn incremented to {self.agent_turns}")

    def record_error(self, error: str) -> None:
        """
        Record last error for debugging.

        Args:
            error: Error message or description
        """
        self.last_error = error
        logger.error(f"Agent error recorded: {error}")

    def has_receipt_data(self) -> bool:
        """Check if receipt OCR has been completed."""
        return self.receipt_data is not None

    def has_bill_split(self) -> bool:
        """Check if bill split has been created."""
        return self.bill_split is not None

    def store_image_bytes(self, image_bytes: bytes) -> None:
        """
        Store downloaded image bytes in session for reuse.

        Args:
            image_bytes: Raw image bytes from Telegram photo
        """
        self.image_bytes = image_bytes
        logger.info(
            f"Stored image bytes in session: {len(image_bytes)} bytes "
            f"({len(image_bytes)/1024:.1f} KB)"
        )

    def has_image_bytes(self) -> bool:
        """Check if image bytes are cached in session."""
        return self.image_bytes is not None
