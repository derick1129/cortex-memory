from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP

from cortex.config import CortexConfig
from cortex.core.hashing import compute_content_hash
from cortex.core.models import EpisodicEvent, EventType, OutcomeStatus
from cortex.engine.consolidation_daemon import ConsolidationDaemon
from cortex.engine.token_budgeter import TokenBudgeter
from cortex.engine.working_memory import WorkingMemoryManager
from cortex.storage.neo4j_store import Neo4jGraphStore
from cortex.storage.postgres_store import PostgresEpisodicStore


def create_cortex_mcp_server(config: Optional[CortexConfig] = None) -> FastMCP:
    cfg = config or CortexConfig()
    mcp = FastMCP("cortex-memory")

    pg_store = PostgresEpisodicStore(cfg.postgres_url)
    neo4j_store = Neo4jGraphStore(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password)
    wm_manager = WorkingMemoryManager(cfg)
    daemon = ConsolidationDaemon(pg_store, neo4j_store, cfg)
    budgeter = TokenBudgeter(cfg.context_budget_ceiling)

    @mcp.tool()
    async def cortex_record_event(
        session_id: str,
        turn_index: int,
        event_type: str,
        payload: Dict[str, Any],
        outcome_status: str,
        target_entity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Hot-path non-blocking episodic event logging."""
        event = EpisodicEvent(
            session_id=session_id,
            turn_index=turn_index,
            event_type=EventType(event_type),
            payload=payload,
            outcome_status=OutcomeStatus(outcome_status),
            target_entity=target_entity,
        )
        await pg_store.connect()
        event_id, content_hash = await pg_store.record_event(event)
        loop_count = await pg_store.check_repetitive_loop(session_id, content_hash)
        return {
            "event_id": str(event_id),
            "content_hash": content_hash,
            "repetitive_loop_detected": loop_count > 1,
            "occurrence_count": loop_count,
        }

    @mcp.tool()
    async def cortex_check_error_loop(session_id: str, error_output: str) -> Dict[str, Any]:
        """Checks if identical error stack trace has occurred previously."""
        await pg_store.connect()
        content_hash = compute_content_hash(error_output)
        count = await pg_store.check_repetitive_loop(session_id, content_hash)
        return {
            "loop_detected": count > 1,
            "occurrence_count": count,
            "content_hash": content_hash,
        }

    @mcp.tool()
    def cortex_update_scratchpad(
        session_id: str,
        active_goal: Optional[str] = None,
        current_hypothesis: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates Tier 1 transient working memory scratchpad."""
        state = wm_manager.update_scratchpad(
            session_id=session_id,
            active_goal=active_goal,
            current_hypothesis=current_hypothesis,
            notes=notes,
        )
        return {"status": "UPDATED", "session_id": state.session_id}

    @mcp.tool()
    async def cortex_query_memory(
        query: str,
        session_id: Optional[str] = None,
        target_entity: Optional[str] = None,
        max_tokens: int = 2000,
    ) -> str:
        """Hybrid 4-tier retrieval returning synthesized, lean context."""
        items: List[Dict[str, str]] = []
        if session_id:
            wm_text = wm_manager.format_context(session_id)
            if wm_text:
                items.append({"section": "Active Working Scratchpad", "content": wm_text})

        await neo4j_store.connect()
        if target_entity:
            deps = await neo4j_store.traverse_dependencies(target_entity)
            if deps:
                dep_summary = "\n".join([f"- {d['name']} (depth {d['depth']})" for d in deps])
                items.append({"section": "Graph Dependencies", "content": dep_summary})

        local_budgeter = TokenBudgeter(max_tokens=max_tokens)
        return local_budgeter.pack(items) if items else "No historical memories found for query."

    @mcp.tool()
    async def cortex_inspect_graph(entity_id: str) -> List[Dict[str, Any]]:
        """Queries bi-temporal knowledge graph dependencies for a code entity."""
        await neo4j_store.connect()
        return await neo4j_store.traverse_dependencies(entity_id)

    @mcp.tool()
    async def cortex_force_consolidation(limit: int = 25) -> Dict[str, Any]:
        """Manually forces background sleep-cycle consolidation."""
        await pg_store.connect()
        await neo4j_store.connect()
        count = await daemon.run_cycle(limit=limit)
        return {"consolidated_count": count}

    return mcp
