import contextlib
import inspect
import json
from typing import Any, AsyncIterator, List, Optional, Tuple
from uuid import UUID
import asyncpg
from cortex.core.models import EpisodicEvent

SCHEMA_DDL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS episodic_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(64) NOT NULL,
    turn_index INTEGER NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,
    recorded_time TIMESTAMPTZ DEFAULT NOW(),
    event_type VARCHAR(32) NOT NULL,
    target_entity VARCHAR(255),
    payload JSONB NOT NULL,
    outcome_status VARCHAR(16) NOT NULL,
    content_hash CHAR(64) NOT NULL,
    consolidated BOOLEAN DEFAULT FALSE,
    consolidated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_episodic_session_time ON episodic_events(session_id, valid_time DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_hash ON episodic_events(content_hash);
CREATE INDEX IF NOT EXISTS idx_episodic_payload_gin ON episodic_events USING GIN (payload);
CREATE INDEX IF NOT EXISTS idx_episodic_unconsolidated ON episodic_events(valid_time ASC) WHERE NOT consolidated;
"""


class PostgresEpisodicStore:
    def __init__(self, postgres_url: str) -> None:
        self.postgres_url = postgres_url
        self._pool: Optional[asyncpg.Pool] = None

    @contextlib.asynccontextmanager
    async def _acquire(self) -> AsyncIterator[Any]:
        assert self._pool is not None, "Postgres pool is not connected"
        ctx = self._pool.acquire()
        if inspect.iscoroutine(ctx):
            ctx = await ctx
        async with ctx as conn:
            yield conn

    async def connect(self) -> None:
        if not self._pool:
            pool = asyncpg.create_pool(self.postgres_url)
            if inspect.iscoroutine(pool):
                pool = await pool
            self._pool = pool

    async def disconnect(self) -> None:
        if self._pool:
            res = self._pool.close()
            if inspect.iscoroutine(res):
                await res
            self._pool = None

    async def initialize_schema(self) -> None:
        async with self._acquire() as conn:
            await conn.execute(SCHEMA_DDL)

    async def record_event(self, event: EpisodicEvent) -> Tuple[UUID, str]:
        event_type_val = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
        outcome_status_val = (
            event.outcome_status.value if hasattr(event.outcome_status, "value") else str(event.outcome_status)
        )
        async with self._acquire() as conn:
            query = """
            INSERT INTO episodic_events (
                event_id, session_id, turn_index, valid_time, recorded_time,
                event_type, target_entity, payload, outcome_status, content_hash
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """
            await conn.execute(
                query,
                event.event_id,
                event.session_id,
                event.turn_index,
                event.valid_time,
                event.recorded_time,
                event_type_val,
                event.target_entity,
                json.dumps(event.payload),
                outcome_status_val,
                event.content_hash,
            )
        return event.event_id, event.content_hash

    async def check_repetitive_loop(self, session_id: str, content_hash: str) -> int:
        async with self._acquire() as conn:
            row = await conn.fetchval(
                """
                SELECT COUNT(*) FROM episodic_events
                WHERE session_id = $1 AND content_hash = $2
                """,
                session_id,
                content_hash,
            )
            return int(row or 0)

    async def fetch_unconsolidated_batch(self, limit: int = 25) -> List[asyncpg.Record]:
        async with self._acquire() as conn:
            return await conn.fetch(
                """
                SELECT event_id, session_id, turn_index, valid_time, event_type,
                       target_entity, payload, outcome_status, content_hash
                FROM episodic_events
                WHERE NOT consolidated
                ORDER BY valid_time ASC
                LIMIT $1
                FOR UPDATE SKIP LOCKED
                """,
                limit,
            )

    async def mark_consolidated(self, event_ids: List[UUID]) -> None:
        async with self._acquire() as conn:
            await conn.execute(
                """
                UPDATE episodic_events
                SET consolidated = TRUE, consolidated_at = NOW()
                WHERE event_id = ANY($1::uuid[])
                """,
                event_ids,
            )
