# CortexMemory

Bi-Temporal, 4-Tier Hybrid Cognitive Memory Engine for Autonomous Coding Agents.

## Architecture
- **Tier 1 (Working Memory):** Sliding context and active goal scratchpad.
- **Tier 2 (Episodic Store):** Append-only PostgreSQL event log with GIN indexing and SHA-256 repetitive error detection.
- **Tier 3 (Semantic Store):** Neo4j native Lucene vector index.
- **Tier 4 (Knowledge Graph):** Bi-temporal Neo4j property graph with `[valid_from, valid_to]` intervals.
- **Sleep-Cycle Daemon:** Asynchronous background distillation via `pg_notify` and atomic reconciliation (ADD, UPDATE, DELETE, NOOP).
- **FastMCP Server:** Model Context Protocol interface exposing 6 tools for coding agents.

## Quickstart
```bash
docker compose -f docker/docker-compose.yml up -d
uv sync
uv run pytest
```
