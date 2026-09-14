from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from cortex.core.hashing import compute_content_hash


class EventType(str, Enum):
    TOOL_CALL = "tool_call"
    USER_PROMPT = "user_prompt"
    GIT_COMMIT = "git_commit"
    TEST_FAILURE = "test_failure"
    FILE_EDIT = "file_edit"


class OutcomeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"


class EpisodicEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    session_id: str
    turn_index: int
    valid_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    recorded_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: EventType
    target_entity: Optional[str] = None
    payload: Dict[str, Any]
    outcome_status: OutcomeStatus
    content_hash: str = ""
    consolidated: bool = False
    consolidated_at: Optional[datetime] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            raw_repr = str(self.payload.get("stderr") or self.payload.get("error") or self.payload)
            self.content_hash = compute_content_hash(raw_repr)


class WorkingMemoryState(BaseModel):
    session_id: str
    active_goal: str = ""
    current_hypothesis: str = ""
    scratchpad_notes: str = ""
    turn_window: List[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GraphNode(BaseModel):
    id: str
    name: str
    labels: List[str]
    properties: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None


class GraphRelationship(BaseModel):
    source_id: str
    target_id: str
    rel_type: str
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_to: Optional[datetime] = None
    confidence: float = 1.0
    properties: Dict[str, Any] = Field(default_factory=dict)


class ReconciliationAction(str, Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NOOP = "NOOP"


class ReconciliationInstruction(BaseModel):
    action: ReconciliationAction
    target_type: str  # 'NODE' | 'RELATIONSHIP'
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    rel_type: Optional[str] = None
    node_data: Optional[GraphNode] = None
    relationship_data: Optional[GraphRelationship] = None
    reasoning: str
