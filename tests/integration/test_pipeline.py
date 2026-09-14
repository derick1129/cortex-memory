import pytest
from cortex.core.models import EpisodicEvent, EventType, OutcomeStatus
from cortex.engine.rrf import fuse_reciprocal_ranks
from cortex.engine.token_budgeter import TokenBudgeter
from cortex.engine.working_memory import WorkingMemoryManager


def test_full_pipeline_contract():
    # 1. Tier 1 Working Memory
    wm = WorkingMemoryManager()
    wm.update_scratchpad("sess_01", active_goal="Implement Auth", notes="Use Bearer tokens")
    scratchpad = wm.format_context("sess_01")
    assert "Implement Auth" in scratchpad

    # 2. Tier 2 Event creation & hashing
    event = EpisodicEvent(
        session_id="sess_01",
        turn_index=1,
        event_type=EventType.TOOL_CALL,
        payload={"command": "npm test", "exit_code": 0},
        outcome_status=OutcomeStatus.SUCCESS,
    )
    assert len(event.content_hash) == 64

    # 3. Tier 3 & Tier 4 Fusion (RRF)
    rankings = {
        "vector": ["src/auth.py", "src/jwt.py"],
        "graph": ["src/jwt.py", "src/auth.py"],
    }
    fused = fuse_reciprocal_ranks(rankings, {"vector": 1.0, "graph": 1.2})
    assert fused[0][0] == "src/jwt.py"

    # 4. Token budgeting
    budgeter = TokenBudgeter(max_tokens=500)
    context = budgeter.pack([
        {"section": "Working Memory", "content": scratchpad},
        {"section": "Dependencies", "content": f"Top match: {fused[0][0]}"},
    ])
    assert "Implement Auth" in context
    assert "src/jwt.py" in context
