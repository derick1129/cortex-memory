from unittest.mock import AsyncMock, patch
import pytest

from cortex.config import CortexConfig
from cortex.mcp.server import create_cortex_mcp_server


def test_mcp_server_initialization():
    server = create_cortex_mcp_server()
    assert server.name == "cortex-memory"


@pytest.mark.asyncio
async def test_mcp_update_scratchpad_tool():
    server = create_cortex_mcp_server()
    tool = server._tool_manager.get_tool("cortex_update_scratchpad")
    assert tool is not None
    result = await tool.run(
        {
            "session_id": "sess_test",
            "active_goal": "Goal 1",
            "current_hypothesis": "Hyp 1",
            "notes": "Note 1",
        }
    )
    assert result["status"] == "UPDATED"
    assert result["session_id"] == "sess_test"


@pytest.mark.asyncio
async def test_mcp_check_error_loop():
    server = create_cortex_mcp_server()
    tool = server._tool_manager.get_tool("cortex_check_error_loop")
    assert tool is not None

    with patch("cortex.storage.postgres_store.PostgresEpisodicStore.connect", new_callable=AsyncMock), \
         patch("cortex.storage.postgres_store.PostgresEpisodicStore.check_repetitive_loop", new_callable=AsyncMock, return_value=3):
        res = await tool.run({"session_id": "sess_test", "error_output": "IndexError: out of range"})
        assert res["loop_detected"] is True
        assert res["occurrence_count"] == 3
        assert len(res["content_hash"]) == 64


@pytest.mark.asyncio
async def test_mcp_record_event():
    server = create_cortex_mcp_server()
    tool = server._tool_manager.get_tool("cortex_record_event")
    assert tool is not None

    with patch("cortex.storage.postgres_store.PostgresEpisodicStore.connect", new_callable=AsyncMock), \
         patch("cortex.storage.postgres_store.PostgresEpisodicStore.record_event", new_callable=AsyncMock, return_value=("uuid-123", "hash-123")), \
         patch("cortex.storage.postgres_store.PostgresEpisodicStore.check_repetitive_loop", new_callable=AsyncMock, return_value=1):
        res = await tool.run({
            "session_id": "sess_test",
            "turn_index": 1,
            "event_type": "tool_call",
            "payload": {"cmd": "pytest"},
            "outcome_status": "SUCCESS",
        })
        assert res["event_id"] == "uuid-123"
        assert res["content_hash"] == "hash-123"
        assert res["repetitive_loop_detected"] is False


@pytest.mark.asyncio
async def test_mcp_query_memory_and_inspect_graph():
    server = create_cortex_mcp_server()
    query_tool = server._tool_manager.get_tool("cortex_query_memory")
    inspect_tool = server._tool_manager.get_tool("cortex_inspect_graph")

    # Update scratchpad
    update_tool = server._tool_manager.get_tool("cortex_update_scratchpad")
    await update_tool.run({"session_id": "sess_test", "active_goal": "Build Auth", "notes": "Use JWT"})

    with patch("cortex.storage.neo4j_store.Neo4jGraphStore.connect", new_callable=AsyncMock), \
         patch("cortex.storage.neo4j_store.Neo4jGraphStore.traverse_dependencies", new_callable=AsyncMock, return_value=[{"name": "jwt.py", "depth": 1}]):
        query_res = await query_tool.run({"query": "Auth", "session_id": "sess_test", "target_entity": "src/auth.py"})
        assert "Build Auth" in query_res
        assert "jwt.py" in query_res

        inspect_res = await inspect_tool.run({"entity_id": "src/auth.py"})
        assert len(inspect_res) == 1
        assert inspect_res[0]["name"] == "jwt.py"


@pytest.mark.asyncio
async def test_mcp_force_consolidation():
    server = create_cortex_mcp_server()
    tool = server._tool_manager.get_tool("cortex_force_consolidation")

    with patch("cortex.storage.postgres_store.PostgresEpisodicStore.connect", new_callable=AsyncMock), \
         patch("cortex.storage.neo4j_store.Neo4jGraphStore.connect", new_callable=AsyncMock), \
         patch("cortex.engine.consolidation_daemon.ConsolidationDaemon.run_cycle", new_callable=AsyncMock, return_value=5):
        res = await tool.run({"limit": 25})
        assert res["consolidated_count"] == 5
