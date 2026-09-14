from datetime import datetime, timezone
from typing import Any, Dict, Optional
from cortex.core.models import WorkingMemoryState
from cortex.config import CortexConfig


class WorkingMemoryManager:
    """Manages ephemeral Tier 1 Working Memory for active sessions."""

    def __init__(self, config: Optional[CortexConfig] = None) -> None:
        self.config = config or CortexConfig()
        self._stores: Dict[str, WorkingMemoryState] = {}

    def get_state(self, session_id: str) -> WorkingMemoryState:
        if session_id not in self._stores:
            self._stores[session_id] = WorkingMemoryState(session_id=session_id)
        return self._stores[session_id]

    def update_scratchpad(
        self,
        session_id: str,
        active_goal: Optional[str] = None,
        current_hypothesis: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> WorkingMemoryState:
        state = self.get_state(session_id)
        if active_goal is not None:
            state.active_goal = active_goal
        if current_hypothesis is not None:
            state.current_hypothesis = current_hypothesis
        if notes is not None:
            state.scratchpad_notes = notes
        state.last_updated = datetime.now(timezone.utc)
        return state

    def enforce_token_budget(self, session_id: str) -> None:
        state = self.get_state(session_id)
        if len(state.turn_window) > 5:
            state.turn_window = state.turn_window[-5:]

    def append_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        state = self.get_state(session_id)
        state.turn_window.append(turn)
        self.enforce_token_budget(session_id)
        state.last_updated = datetime.now(timezone.utc)

    def format_context(self, session_id: str) -> str:
        state = self.get_state(session_id)
        sections = []
        if state.active_goal:
            sections.append(f"**Active Goal:** {state.active_goal}")
        if state.current_hypothesis:
            sections.append(f"**Current Hypothesis:** {state.current_hypothesis}")
        if state.scratchpad_notes:
            sections.append(f"**Scratchpad Notes:**\n{state.scratchpad_notes}")
        return "\n\n".join(sections)
