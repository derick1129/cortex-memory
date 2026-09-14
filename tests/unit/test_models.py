from datetime import datetime, timezone
from uuid import UUID
from cortex.core.models import EpisodicEvent, WorkingMemoryState, GraphRelationship


def test_episodic_event_creation():
    event = EpisodicEvent(
        session_id="sess_123",
        turn_index=1,
        valid_time=datetime.now(timezone.utc),
        event_type="test_failure",
        payload={"stderr": "AssertionError: 404 != 200"},
        outcome_status="FAILED",
    )
    assert isinstance(event.event_id, UUID)
    assert len(event.content_hash) == 64
    assert event.consolidated is False
