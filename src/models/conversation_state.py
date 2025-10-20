"""Conversation state models for managing bill splitting workflow."""

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.bill import Receipt


class ConversationStep(str, Enum):
    """Enum representing the current step in the bill splitting conversation."""

    IDLE = "idle"
    AWAITING_RECEIPT = "awaiting_receipt"
    AWAITING_DESCRIPTION = "awaiting_description"
    AWAITING_BOTH = "awaiting_both"
    PROCESSING = "processing"


class BillSession:
    """Represents an active bill splitting session for a user."""

    def __init__(self) -> None:
        """Initialize a new bill session."""
        self.step: ConversationStep = ConversationStep.IDLE
        self.receipt_file_id: str | None = None
        self.receipt_data: "Receipt | None" = None
        self.participant_description: str | None = None

    def reset(self) -> None:
        """Reset the session to initial state."""
        self.step = ConversationStep.IDLE
        self.receipt_file_id = None
        self.receipt_data = None
        self.participant_description = None

    def start_new_bill(self) -> None:
        """Start a new bill splitting workflow."""
        self.reset()
        self.step = ConversationStep.AWAITING_BOTH

    def set_receipt(self, file_id: str, receipt_data: "Receipt") -> None:
        """
        Store receipt data. If description exists, move to processing.
        Otherwise, wait for description.
        """
        self.receipt_file_id = file_id
        self.receipt_data = receipt_data

        if self.participant_description is not None:
            # Both receipt and description are present
            self.step = ConversationStep.PROCESSING
        else:
            # Still waiting for description
            self.step = ConversationStep.AWAITING_DESCRIPTION

    def set_description(self, description: str) -> None:
        """
        Store participant description. If receipt exists, move to processing.
        Otherwise, wait for receipt.
        """
        self.participant_description = description

        if self.receipt_data is not None:
            # Both receipt and description are present
            self.step = ConversationStep.PROCESSING
        else:
            # Still waiting for receipt
            self.step = ConversationStep.AWAITING_RECEIPT

    def is_ready_for_processing(self) -> bool:
        """Check if session has all required data for processing."""
        return (
            self.receipt_data is not None
            and self.participant_description is not None
            and self.step == ConversationStep.PROCESSING
        )
