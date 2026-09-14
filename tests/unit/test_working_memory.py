from cortex.engine.working_memory import WorkingMemoryManager
from cortex.config import CortexConfig


def test_working_memory_update_and_retrieval():
    config = CortexConfig(working_memory_token_cap=500)
    manager = WorkingMemoryManager(config=config)

    manager.update_scratchpad(
        session_id="test_sess",
        active_goal="Refactor DB Layer",
        current_hypothesis="Connection pool exhaustion",
        notes="Check max_connections setting",
    )

    state = manager.get_state("test_sess")
    assert state.active_goal == "Refactor DB Layer"
    assert state.current_hypothesis == "Connection pool exhaustion"
    assert "Check max_connections" in state.scratchpad_notes


def test_working_memory_turn_sliding_window():
    config = CortexConfig(working_memory_token_cap=100)
    manager = WorkingMemoryManager(config=config)

    for i in range(10):
        manager.append_turn("test_sess", {"role": "user", "content": f"Turn {i}"})

    state = manager.get_state("test_sess")
    # sliding window should keep at most 5 recent turns
    assert len(state.turn_window) <= 5
    assert state.turn_window[-1] == {"role": "user", "content": "Turn 9"}
    assert state.turn_window[0] == {"role": "user", "content": "Turn 5"}


def test_working_memory_format_context():
    manager = WorkingMemoryManager()
    manager.update_scratchpad(
        session_id="test_sess",
        active_goal="Implement Auth",
        current_hypothesis="JWT token expired",
        notes="Use Bearer tokens in header",
    )

    formatted = manager.format_context("test_sess")
    assert "**Active Goal:** Implement Auth" in formatted
    assert "**Current Hypothesis:** JWT token expired" in formatted
    assert "**Scratchpad Notes:**\nUse Bearer tokens in header" in formatted


def test_working_memory_format_context_empty():
    manager = WorkingMemoryManager()
    assert manager.format_context("empty_sess") == ""


def test_working_memory_partial_updates():
    manager = WorkingMemoryManager()
    manager.update_scratchpad(
        session_id="test_sess",
        active_goal="Initial Goal",
        notes="Initial Notes",
    )

    # Update only hypothesis
    manager.update_scratchpad(
        session_id="test_sess",
        current_hypothesis="Hypothesis 1",
    )

    state = manager.get_state("test_sess")
    assert state.active_goal == "Initial Goal"
    assert state.current_hypothesis == "Hypothesis 1"
    assert state.scratchpad_notes == "Initial Notes"


def test_working_memory_enforce_token_budget():
    manager = WorkingMemoryManager()
    state = manager.get_state("sess_budget")
    for i in range(8):
        state.turn_window.append({"turn": i})
    assert len(state.turn_window) == 8

    manager.enforce_token_budget("sess_budget")
    assert len(state.turn_window) == 5
    assert state.turn_window[0] == {"turn": 3}
    assert state.turn_window[-1] == {"turn": 7}
