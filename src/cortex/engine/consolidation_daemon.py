import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from cortex.config import CortexConfig
from cortex.core.models import (
    GraphNode,
    GraphRelationship,
    ReconciliationAction,
    ReconciliationInstruction,
)
from cortex.storage.neo4j_store import Neo4jGraphStore
from cortex.storage.postgres_store import PostgresEpisodicStore

CONSOLIDATION_PROMPT = """
You are the CortexMemory Cognitive Reflection Daemon.
Review the following batch of episodic events from a coding session and extract lasting architectural knowledge.
Output a JSON array of reconciliation operations:
- ADD: new node or relationship
- UPDATE: update node properties
- DELETE: invalidate existing superseded relationship (set valid_to)
- NOOP: ephemeral action that requires no graph mutation

JSON Format:
[
  {
    "action": "ADD" | "UPDATE" | "DELETE" | "NOOP",
    "target_type": "NODE" | "RELATIONSHIP",
    "source_id": "...",
    "target_id": "...",
    "rel_type": "...",
    "node_data": { "id": "...", "name": "...", "labels": ["..."], "properties": {} },
    "relationship_data": { "source_id": "...", "target_id": "...", "rel_type": "...", "confidence": 1.0 },
    "reasoning": "..."
  }
]
"""


class ConsolidationDaemon:
    def __init__(
        self,
        postgres_store: PostgresEpisodicStore,
        neo4j_store: Neo4jGraphStore,
        config: Optional[CortexConfig] = None,
    ) -> None:
        self.pg = postgres_store
        self.neo4j = neo4j_store
        self.config = config or CortexConfig()
        self._running = False

    async def apply_reconciliation(self, instructions: List[ReconciliationInstruction]) -> Dict[str, int]:
        counts = {"added": 0, "updated": 0, "invalidated": 0, "noop": 0}
        for inst in instructions:
            if inst.action == ReconciliationAction.NOOP:
                counts["noop"] += 1
                continue
            if inst.action == ReconciliationAction.DELETE and inst.target_type == "RELATIONSHIP":
                assert inst.source_id and inst.target_id and inst.rel_type
                await self.neo4j.invalidate_relationship(inst.source_id, inst.target_id, inst.rel_type)
                counts["invalidated"] += 1
            elif inst.action == ReconciliationAction.ADD and inst.target_type == "NODE" and inst.node_data:
                await self.neo4j.upsert_node(inst.node_data)
                counts["added"] += 1
            elif inst.action == ReconciliationAction.ADD and inst.target_type == "RELATIONSHIP" and inst.relationship_data:
                await self.neo4j.create_bi_temporal_relationship(inst.relationship_data)
                counts["added"] += 1
        return counts

    async def run_cycle(self, limit: int = 25) -> int:
        records = await self.pg.fetch_unconsolidated_batch(limit=limit)
        if not records:
            return 0
        event_ids: List[UUID] = [r["event_id"] for r in records]

        # Distill structural knowledge from file edits/commits
        instructions: List[ReconciliationInstruction] = []
        for r in records:
            target = r["target_entity"]
            if target and r["event_type"] in ("file_edit", "git_commit"):
                instructions.append(
                    ReconciliationInstruction(
                        action=ReconciliationAction.ADD,
                        target_type="NODE",
                        node_data=GraphNode(
                            id=target,
                            name=target.split("/")[-1],
                            labels=["CodeEntity"],
                            properties={"last_seen": datetime.now(timezone.utc).isoformat()},
                        ),
                        reasoning=f"Entity updated in event {r['event_id']}",
                    )
                )

        if instructions:
            await self.apply_reconciliation(instructions)
        await self.pg.mark_consolidated(event_ids)
        return len(event_ids)
