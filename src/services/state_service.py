from typing import Dict, Optional
from src.models.state import BillState, UserState

class StateService:
    """Service to manage user states."""

    def __init__(self):
        self._user_states: Dict[int, UserState] = {}

    def get_state(self, user_id: int) -> UserState:
        """Get the current state for a user. Creates a new state if none exists."""
        if user_id not in self._user_states:
            self._user_states[user_id] = UserState()
        return self._user_states[user_id]

    def set_state(self, user_id: int, state: BillState) -> None:
        """Set the state for a user."""
        user_state = self.get_state(user_id)
        user_state.state = state

    def update_data(self, user_id: int, description: str) -> None:
        """Update the description data for a user."""
        user_state = self.get_state(user_id)
        user_state.description = description

    def clear_state(self, user_id: int) -> None:
        """Reset the state for a user to IDLE and clear data."""
        if user_id in self._user_states:
            self._user_states[user_id] = UserState()
