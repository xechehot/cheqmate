"""Conversation state models for managing bill splitting workflow."""

from enum import Enum


class ConversationStep(str, Enum):
    """Enum representing the current step in the bill splitting conversation."""

    IDLE = "idle"
    AWAITING_DESCRIPTION = "awaiting_description"
    AWAITING_RECEIPT = "awaiting_receipt"
    PROCESSING = "processing"


class BillSession:
    """Represents an active bill splitting session for a user."""

    def __init__(self) -> None:
        """Initialize a new bill session."""
        self.step: ConversationStep = ConversationStep.IDLE
        self.participant_description: str | None = None
        self.receipt_file_id: str | None = None

    def reset(self) -> None:
        """Reset the session to initial state."""
        self.step = ConversationStep.IDLE
        self.participant_description = None
        self.receipt_file_id = None

    def start_new_bill(self) -> None:
        """Start a new bill splitting workflow."""
        self.reset()
        self.step = ConversationStep.AWAITING_RECEIPT

    def set_receipt(self, file_id: str) -> None:
        """Store receipt file ID and move to next step."""
        self.receipt_file_id = file_id
        self.step = ConversationStep.AWAITING_DESCRIPTION

    def set_description(self, description: str) -> None:
        """Store participant description and move to processing."""
        self.participant_description = description
        self.step = ConversationStep.PROCESSING

    def is_ready_for_processing(self) -> bool:
        """Check if session has all required data for processing."""
        return (
            self.participant_description is not None
            and self.receipt_file_id is not None
            and self.step == ConversationStep.PROCESSING
        )
