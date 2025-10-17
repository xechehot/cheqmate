"""Conversation state models for managing receipt recognition workflow."""

from enum import Enum


class ConversationStep(str, Enum):
    """Enum representing the current step in the receipt recognition conversation."""

    IDLE = "idle"
    AWAITING_RECEIPT = "awaiting_receipt"
    PROCESSING = "processing"


class BillSession:
    """Represents an active receipt recognition session for a user."""

    def __init__(self) -> None:
        """Initialize a new receipt session."""
        self.step: ConversationStep = ConversationStep.IDLE
        self.receipt_file_id: str | None = None

    def reset(self) -> None:
        """Reset the session to initial state."""
        self.step = ConversationStep.IDLE
        self.receipt_file_id = None

    def start_new_bill(self) -> None:
        """Start a new receipt recognition workflow."""
        self.reset()
        self.step = ConversationStep.AWAITING_RECEIPT

    def set_receipt(self, file_id: str) -> None:
        """Store receipt file ID and move to processing."""
        self.receipt_file_id = file_id
        self.step = ConversationStep.PROCESSING

    def is_ready_for_processing(self) -> bool:
        """Check if session has all required data for processing."""
        return (
            self.receipt_file_id is not None
            and self.step == ConversationStep.PROCESSING
        )
