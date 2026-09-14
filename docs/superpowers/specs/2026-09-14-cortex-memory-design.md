# CortexMemory: Bi-Temporal, 4-Tier Hybrid Cognitive Memory Engine — System Specification

**Document Version:** 1.0.0  
**Date:** 2026-09-14  
**Status:** Approved Specification  
**Reference Architecture:** [memory_architecture_deep_dive.md](file:///Users/supreme/Dev/cortex-memory/memory_architecture_deep_dive.md) & [cortexmemory_neo4j_postgres_1788856579091.jpg](file:///Users/supreme/Dev/cortex-memory/cortexmemory_neo4j_postgres_1788856579091.jpg)

---

## 1. Executive Summary & Problem Formulation

### 1.1 The Flat-Context Scaling Problem
Modern autonomous coding agents (e.g., Claude Code, Cursor, Windsurf, Antigravity) default to accumulating context linearly within a single ephemeral window:
$$\text{Cumulative Input Tokens}(N) = \sum_{k=1}^{N} \left( T_{\text{system}} + T_{\text{rules}} + k \cdot T_{\text{turn}} \right) = N \cdot (T_{\text{system}} + T_{\text{rules}}) + \frac{N(N+1)}{2} T_{\text{turn}}$$

When cumulative context approaches the model token boundary ($C_{\max} \approx 160\text{k}-200\text{k}$ tokens), agents perform **lossy compaction** down to $\approx 30\text{k}$ tokens. This creates three critical pathologies:
1. **Compaction Amnesia:** Loss of structural dependencies, early user constraints, test execution outputs, and architectural rationale.
2. **Repetitive Debugging Loops:** The agent repeats failed fixes because previous error stack traces and bash outcomes rolled off the compacted context.
3. **Temporal Confusion:** The agent cannot differentiate active code/conventions from superseded designs (e.g. attempting to use REST when the codebase was refactored to tRPC 20 turns ago).

### 1.2 The CortexMemory Solution
CortexMemory decouples working context from long-term memory via a **4-Tier Bi-Temporal Cognitive Memory Architecture**:
- **$O(1)$ Stationary Context Size:** The agent prompt stays lean ($\approx 8\text{k}-12\text{k}$ tokens per turn) while maintaining lossless access to all historical events.
- **Bi-Temporal Correctness:** Tracks both real-world validity time ($t_{\text{valid}}$: `[valid_from, valid_to]`) and transaction capture time ($t_{\text{record}}$), enabling point-in-time consistency and automatic supersedence detection.
- **Sub-Second RRF Retrieval:** Combines graph path traversal, native vector cosine similarity, and episodic hash matching into a single token-budgeted injection.
- **Zero-Polling Reactive Consolidation:** Background "sleep-cycle" consolidation runs asynchronously via PostgreSQL `LISTEN`/`NOTIFY`, keeping the hot execution path non-blocking.

---

## 2. High-Level Architecture & Data Flow

```
                           Agent Action / Query
                     (Context + Timestamp [t_now])
                                  │
                                  ▼
               ┌──────────────────────────────────────┐
               │       Cognitive Memory Router        │
               │   {intent, entity, temporal_scope}   │
               └────┬────────────┬───────────┬────┬───┘
                    │            │           │    │
          hot_read  │episodic_log│vec_search │    │ graph_traverse
                    ▼            │           ▼    ▼
 ┌───────────────────────────┐   │   ┌───────────────────────────┐
 │ Tier 1: Working Memory    │   │   │ Tier 3: Semantic Store    │
 │ (Sliding Context Scratch) │   │   │ (Neo4j Vector Index)      │
 └───────────────────────────┘   │   └───────────────────────────┘
                                 ▼                 │
 ┌──────────────────────────────────────────────┐  │
 │ Tier 2: Episodic Store (PostgreSQL)          │  │
 │ - Append-only JSONB Event Log                │  │
 │ - Content Hash Deduplication (SHA-256)       │  │
 │ - pg_notify('new_episode_channel')           │  │
 └───────────────────────┬──────────────────────┘  │
                         │                         │
                         ▼ (LISTEN notification)   │
 ┌─────────────────────────────────────────────┐   │
 │ Async Sleep-Cycle Consolidation Daemon      │   │
 │ - Extract & Reflect (Salient Facts)         │   │
 │ - Reconcile (ADD, UPDATE, DELETE, NOOP)     │   │
 └───────────────────────┬─────────────────────┘   │
                         │ (Writes distilled facts)│
                         ▼                         ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ Tier 4: Knowledge Graph (Bi-Temporal Neo4j DB)                │
 │ - [valid_from, valid_to] intervals, structural dependencies   │
 └───────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ Reciprocal Rank Fusion (RRF) & Guardrails                     │
 │ - Temporal Validity Filter (valid_to IS NULL OR > t_now)      │
 │ - Token Budgeter (packs facts into <= Token Ceiling)          │
 └───────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
                     Synthesized Context Output
                 (FastMCP Tool Response to Agent)
```

---

## 3. Detailed Component Specifications

### 3.1 Tier 1: Working Memory (Sliding Context & Scratchpad)
- **Role:** High-speed transient working memory for the active agent session.
- **Persistence:** Local in-memory dictionary backed by Redis or an active JSON state file per session.
- **Components:**
  - `active_goal`: High-level goal (e.g. "Migrate Auth from JWT to Session Cookies").
  - `current_hypothesis`: Current line of reasoning or active debugging hypothesis.
  - `scratchpad_notes`: Ephemeral developer thoughts or command outputs.
  - `turn_window`: Last $K$ turns (default $K=3$) of user/assistant raw interactions.
- **Capacity Constraint:** Strictly hard-capped at $4{,}000$ tokens. When exceeded, oldest ephemeral turns roll out; key findings are promoted to Tier 2.

### 3.2 Tier 2: Episodic Store (PostgreSQL Event Log)
- **Role:** Lossless, append-only operational audit trail of every interaction, tool execution, bash command, git diff, and error.
- **Database Engine:** PostgreSQL 16+ with extensions `uuid-ossp` and `pgcrypto`.
- **Relational Schema:**
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE episodic_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(64) NOT NULL,
    turn_index INTEGER NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,            -- Real-world occurrence time
    recorded_time TIMESTAMPTZ DEFAULT NOW(),       -- Database transaction time
    event_type VARCHAR(32) NOT NULL,            -- 'tool_call', 'user_prompt', 'git_commit', 'test_failure', 'file_edit'
    target_entity VARCHAR(255),                 -- File path, module, or test suite
    payload JSONB NOT NULL,                     -- Raw arguments, stdout/stderr, diffs, exit codes
    outcome_status VARCHAR(16) NOT NULL,        -- 'SUCCESS', 'FAILED', 'PENDING'
    content_hash CHAR(64) NOT NULL,             -- SHA-256 hash of error/diff/output
    consolidated BOOLEAN DEFAULT FALSE,         -- Consolidation flag
    consolidated_at TIMESTAMPTZ                 -- Timestamp of background processing
);

-- Indices for low-latency queries
CREATE INDEX idx_episodic_session_time ON episodic_events(session_id, valid_time DESC);
CREATE INDEX idx_episodic_hash ON episodic_events(content_hash);
CREATE INDEX idx_episodic_payload_gin ON episodic_events USING GIN (payload);
CREATE INDEX idx_episodic_unconsolidated ON episodic_events(valid_time ASC) WHERE NOT consolidated;

-- Reactive Event Notification
CREATE OR REPLACE FUNCTION notify_episodic_event()
RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('new_episode_channel', NEW.event_id::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_episodic_event_notify
AFTER INSERT ON episodic_events
FOR EACH ROW EXECUTE FUNCTION notify_episodic_event();
```
- **Repetitive Error Detection:** Queries `idx_episodic_hash` with SHA-256 of stack trace/compiler error. If count $> 1$ within current session, immediately flags `REPETITIVE_FAILURE_LOOP` to the router.

### 3.3 Tier 3: Semantic Store (Neo4j Vector Index)
- **Role:** Dense vector similarity search across code entities, architectural patterns, and error remediation memories.
- **Index Engine:** Neo4j 5.x Native Lucene-backed Vector Index.
- **Configuration:**
  - Embedding Model: 1536-dimensional (OpenAI `text-embedding-3-small` or local FastEmbed `BAAI/bge-small-en-v1.5`).
  - Metric: Cosine similarity.
```cypher
CREATE VECTOR INDEX entity_embeddings IF NOT EXISTS
FOR (e:CodeEntity) ON (e.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX decision_embeddings IF NOT EXISTS
FOR (d:ArchitecturalDecision) ON (d.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};
```

### 3.4 Tier 4: Knowledge Graph (Bi-Temporal Neo4j DB)
- **Role:** Structural dependency representation, multi-hop architectural queries, and historical evolution tracking.
- **Node Labels:**
  - `:CodeEntity` (`id`, `name`, `type: 'file'|'function'|'class'|'module'`, `path`, `embedding`)
  - `:ArchitecturalDecision` (`id`, `title`, `description`, `status`, `valid_from`, `valid_to`, `embedding`)
  - `:ErrorPattern` (`id`, `signature_hash`, `error_type`, `stack_summary`, `remedy`)
  - `:Protocol` (`name`)
  - `:Service` (`name`)
- **Bi-Temporal Edge Model:**
  Every relationship represents structural semantics valid over a time interval:
  - `valid_from: datetime` (timestamp when relationship became effective)
  - `valid_to: datetime | null` (`null` indicates currently active/valid; non-null timestamp indicates deprecation/supersedence)
  - `recorded_at: datetime` (when the graph transaction committed)
  - `confidence: float` (0.0 to 1.0 confidence score from consolidation reflection)
- **Key Relationships:**
  - `(:CodeEntity)-[:DEPENDS_ON {valid_from, valid_to, confidence, call_pattern}]->(:CodeEntity)`
  - `(:CodeEntity)-[:MUTATES {valid_from, valid_to}]->(:CodeEntity)`
  - `(:ArchitecturalDecision)-[:SUPERSEDES {valid_from, valid_to}]->(:ArchitecturalDecision)`
  - `(:CodeEntity)-[:USES_PROTOCOL {valid_from, valid_to}]->(:Protocol)`
  - `(:ErrorPattern)-[:RESOLVED_BY {valid_from, valid_to}]->(:CodeEntity)`

---

## 4. Async Sleep-Cycle Consolidation Daemon

### 4.1 Trigger & Queue Processing
1. The daemon maintains an active `asyncpg` listener on PostgreSQL channel `new_episode_channel`.
2. When a notification is received, or every $30$ seconds (fallback timer), the worker executes a concurrency-safe batch query using PostgreSQL MVCC row-level locking:
```sql
SELECT event_id, session_id, turn_index, valid_time, event_type, target_entity, payload, outcome_status
FROM episodic_events
WHERE NOT consolidated
ORDER BY valid_time ASC
LIMIT 25
FOR UPDATE SKIP LOCKED;
```
3. Multi-worker safe: `SKIP LOCKED` prevents duplicate work across horizontal daemon replicas.

### 4.2 Two-Phase Distillation Pipeline
The worker uses a fast, lightweight reasoning model (Claude 3.5 Haiku or Gemini 2.5 Flash / GPT-4o-mini).

#### Phase A: Extract & Reflect
Analyzes episodic payloads (git diffs, tool executions, error logs, user decisions) and extracts:
- New code entities or modules created/modified.
- Architectural conventions established (e.g., "All endpoints must use Zod validation").
- Superseded patterns (e.g., "Deprecated REST endpoint `/api/v1/auth`, replaced with `/api/v2/auth`").
- Successful error remedies.

#### Phase B: Reconcile (The 4 Atomic Operations)
Outputs a structured JSON array of reconciliation instructions:
1. **`ADD`**: Create a new node or relationship with `valid_from = event.valid_time, valid_to = NULL`.
2. **`UPDATE`**: Update node properties (e.g. documentation, signature) or bump relationship confidence.
3. **`DELETE`** (Soft Invalidation): Update existing relationship setting `valid_to = event.valid_time`. Ensures historical auditability without destructive graph deletion.
4. **`NOOP`**: Ephemeral actions (e.g. directory listing, reading unchanged configuration) that do not alter the cognitive graph.

#### Phase C: Transaction Commit
1. Executes Cypher write batch in Neo4j with updated vector embeddings.
2. Updates PostgreSQL:
```sql
UPDATE episodic_events
SET consolidated = TRUE, consolidated_at = NOW()
WHERE event_id = ANY($1::uuid[]);
```

---

## 5. Retrieval, Reciprocal Rank Fusion (RRF) & Token Budgeter

### 5.1 Multi-Modal Query Execution
When the agent invokes `cortex_query_memory(query, entity_target, temporal_point)`:
1. **Vector Retrieval (Tier 3):** Embeds `query` and searches `entity_embeddings` and `decision_embeddings` using cosine similarity (Top $K_v = 15$).
2. **Graph Traversal (Tier 4):** If `entity_target` is provided, traverses bi-temporal dependency neighbors up to 2 hops:
```cypher
MATCH (target:CodeEntity {id: $entity_id})-[r:DEPENDS_ON|USES_PROTOCOL*1..2]-(neighbor:CodeEntity)
WHERE (r[0].valid_to IS NULL OR r[0].valid_to > $temporal_point)
  AND (size(r) = 1 OR r[1].valid_to IS NULL OR r[1].valid_to > $temporal_point)
RETURN neighbor, r, length(path) AS depth
LIMIT 15;
```
3. **Episodic Error Check (Tier 2):** Scans for matching error signatures or past failures related to `entity_target`.

### 5.2 Reciprocal Rank Fusion (RRF) Formula
Combines heterogeneous rankings into a single sorted relevance list:
$$RRF(d) = \sum_{m \in \{\text{vector}, \text{graph}, \text{episodic}\}} \frac{w_m}{k + \text{rank}_m(d)}$$
- Constant $k = 60$.
- Weights: $w_{\text{vector}} = 1.0$, $w_{\text{graph}} = 1.2$, $w_{\text{episodic}} = 0.8$.

### 5.3 Temporal Validity Filter & Token Budgeter
- **Temporal Filter:** Drops any graph fact where $t_{\text{query}} < \text{valid\_from}$ or ($t_{\text{query}} \ge \text{valid\_to}$ and $\text{valid\_to}$ is not null), unless the agent explicitly requested historical point-in-time mode.
- **Token Budgeter:**
  - Maximum Output Limit: Hard ceiling of $2{,}500$ tokens.
  - Formats top-ranked facts into concise markdown sections:
    - `[Active Architectural Constraints]`
    - `[Code Dependencies & Interfaces]`
    - `[Known Gotchas & Past Remedies]`
    - `[Active Working Scratchpad]`

---

## 6. FastMCP Server Specification & Tool Contracts

The server exposes 6 high-performance async tools over stdio/SSE:

### 6.1 `cortex_record_event`
- **Description:** Hot-path ingestion for tool executions, git commits, user requests, and test results.
- **Parameters:**
  - `session_id` (str, required): Active session identifier.
  - `turn_index` (int, required): Current conversational turn index.
  - `event_type` (enum: `'tool_call'|'user_prompt'|'git_commit'|'test_failure'|'file_edit'`, required).
  - `target_entity` (str, optional): Target file or function name.
  - `payload` (dict, required): Detailed JSON execution data.
  - `outcome_status` (enum: `'SUCCESS'|'FAILED'|'PENDING'`, required).
- **Return:** `{"event_id": str, "content_hash": str, "repetitive_loop_detected": bool}`.

### 6.2 `cortex_query_memory`
- **Description:** Hybrid multi-tier retrieval fusing vector search, graph dependencies, and temporal filters.
- **Parameters:**
  - `query` (str, required): Natural language search query or problem description.
  - `target_entity` (str, optional): File path or module name to anchor graph traversal.
  - `temporal_point` (ISO 8601 string, optional): Real-world timestamp for historical retrieval (defaults to current time).
  - `max_tokens` (int, optional, default=2000): Token budget ceiling.
- **Return:** Formatted markdown context injection ready for agent prompt.

### 6.3 `cortex_check_error_loop`
- **Description:** Instant hash check to verify if the current failure has been encountered previously in this session or repository.
- **Parameters:**
  - `session_id` (str, required).
  - `error_output` (str, required): Raw stack trace or compiler diagnostic message.
- **Return:** `{"loop_detected": bool, "occurrence_count": int, "previous_remedies": list[str]}`.

### 6.4 `cortex_update_scratchpad`
- **Description:** Sets or updates Tier 1 working memory (hypotheses, active goals, transient notes).
- **Parameters:**
  - `session_id` (str, required).
  - `active_goal` (str, optional).
  - `current_hypothesis` (str, optional).
  - `notes` (str, optional).
- **Return:** `{"status": "UPDATED", "token_count": int}`.

### 6.5 `cortex_inspect_graph`
- **Description:** Executes targeted Cypher or dependency analysis on the bi-temporal knowledge graph.
- **Parameters:**
  - `entity_id` (str, required): Node identifier (e.g. file path or function).
  - `relationship_types` (list[str], optional): e.g. `['DEPENDS_ON', 'MUTATES']`.
  - `direction` (enum: `'OUTGOING'|'INCOMING'|'BOTH'`, default='BOTH').
  - `include_historical` (bool, default=false): Include superseded edges.
- **Return:** Node attributes, adjacent nodes, edge intervals, and active status.

### 6.6 `cortex_force_consolidation`
- **Description:** Manually triggers background sleep-cycle distillation for all pending unconsolidated events.
- **Parameters:**
  - `session_id` (str, optional): Restrict consolidation to specific session.
- **Return:** `{"events_consolidated": int, "graph_mutations": {"added": int, "updated": int, "invalidated": int}}`.

---

## 7. Infrastructure & Deployment Topology

### 7.1 Docker Compose Services
- **`cortex-postgres`**: PostgreSQL 16 Alpine with pre-initialized schemas, GIN indices, and notify triggers.
- **`cortex-neo4j`**: Neo4j 5.26 Community with APOC plugins, native Lucene vector index, and bi-temporal constraints.
- **`cortex-daemon`**: Python 3.12+ async consolidation worker running `LISTEN new_episode_channel`.
- **`cortex-mcp`**: FastMCP server process serving Claude Code / agent clients via stdio or SSE.

### 7.2 Directory Structure
```
cortex-memory/
├── docker/
│   ├── docker-compose.yml
│   └── postgres-init/
│       └── 01-schema.sql
├── src/
│   └── cortex/
│       ├── __init__.py
│       ├── config.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   └── hashing.py
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── postgres_store.py
│       │   └── neo4j_store.py
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── router.py
│       │   ├── rrf_synthesizer.py
│       │   ├── token_budgeter.py
│       │   └── consolidation_daemon.py
│       ├── mcp/
│       │   ├── __init__.py
│       │   └── server.py
│       └── cli.py
├── tests/
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_hashing.py
│   │   ├── test_rrf.py
│   │   └── test_token_budgeter.py
│   └── integration/
│       ├── test_postgres_store.py
│       ├── test_neo4j_store.py
│       └── test_mcp_tools.py
├── pyproject.toml
├── README.md
└── .env.example
```

---

## 8. Failure Modes, Edge Cases, & Concurrency Control

1. **PostgreSQL LISTEN Drop / Reconnect:**
   If the daemon disconnects from PostgreSQL (e.g. database restart), an exponential backoff reconnect loop re-establishes `LISTEN` and automatically runs a fallback poll query (`WHERE NOT consolidated`) to ensure zero dropped events.
2. **Neo4j Transaction Failures:**
   If a Cypher write fails during consolidation, the PostgreSQL transaction does NOT mark the episodes as `consolidated = TRUE`. The batch is retried on the next cycle.
3. **High-Frequency Bursts:**
   `pg_notify` payloads are lightweight event IDs. Even with 100 tool calls per second, the daemon batches up to 50 events in a single LLM reflection call, avoiding token exhaustion or rate limits.
4. **Cycle & Deadlock Prevention:**
   Dependency edges maintain directional DAG consistency; cyclical dependencies are detected and flagged during consolidation reflection.
