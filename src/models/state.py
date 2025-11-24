from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional

class BillState(Enum):
    """Enum representing the state of a user's bill processing workflow."""
    IDLE = auto()
    WAITING_FOR_DESCRIPTION = auto()
    WAITING_FOR_CHECK = auto()

@dataclass
class UserState:
    """Class to hold the state and data for a user."""
    state: BillState = BillState.IDLE
    description: Optional[str] = None
