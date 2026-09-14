from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from cortex.core.models import (
    GraphNode,
    GraphRelationship,
    ReconciliationAction,
    ReconciliationInstruction,
)
from cortex.engine.consolidation_daemon import ConsolidationDaemon


@pytest.mark.asyncio
async def test_reconciliation_execution_add_and_delete():
    mock_pg = AsyncMock()
    mock_neo4j = AsyncMock()
    daemon = ConsolidationDaemon(postgres_store=mock_pg, neo4j_store=mock_neo4j)

    instructions = [
        ReconciliationInstruction(
            action=ReconciliationAction.DELETE,
            target_type="RELATIONSHIP",
            source_id="src/api.py",
            target_id="src/old_auth.py",
            rel_type="DEPENDS_ON",
            reasoning="Refactored out old auth",
        ),
        ReconciliationInstruction(
            action=ReconciliationAction.ADD,
            target_type="NODE",
            node_data=GraphNode(
                id="src/new_auth.py",
                name="new_auth.py",
                labels=["CodeEntity"],
            ),
            reasoning="Created new auth module",
        ),
        ReconciliationInstruction(
            action=ReconciliationAction.ADD,
            target_type="RELATIONSHIP",
            relationship_data=GraphRelationship(
                source_id="src/api.py",
                target_id="src/new_auth.py",
                rel_type="DEPENDS_ON",
            ),
            reasoning="Wired dependency",
        ),
        ReconciliationInstruction(
            action=ReconciliationAction.NOOP,
            target_type="NODE",
            reasoning="Nothing to do",
        ),
    ]

    counts = await daemon.apply_reconciliation(instructions)
    assert counts["invalidated"] == 1
    assert counts["added"] == 2
    assert counts["noop"] == 1
    assert mock_neo4j.invalidate_relationship.called
    assert mock_neo4j.upsert_node.called
    assert mock_neo4j.create_bi_temporal_relationship.called


@pytest.mark.asyncio
async def test_run_cycle_with_unconsolidated_events():
    mock_pg = AsyncMock()
    mock_neo4j = AsyncMock()
    daemon = ConsolidationDaemon(postgres_store=mock_pg, neo4j_store=mock_neo4j)

    records = [
        {
            "event_id": "00000000-0000-0000-0000-000000000001",
            "session_id": "sess_1",
            "turn_index": 1,
            "valid_time": datetime.now(timezone.utc),
            "event_type": "file_edit",
            "target_entity": "src/auth.py",
            "payload": {},
            "outcome_status": "SUCCESS",
            "content_hash": "abc",
        }
    ]
    mock_pg.fetch_unconsolidated_batch.return_value = records

    count = await daemon.run_cycle(limit=10)
    assert count == 1
    assert mock_pg.mark_consolidated.called
    assert mock_neo4j.upsert_node.called
