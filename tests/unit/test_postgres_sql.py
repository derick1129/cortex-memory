from unittest.mock import AsyncMock, patch
from uuid import uuid4
import pytest

from cortex.core.models import EpisodicEvent, EventType, OutcomeStatus
from cortex.storage.postgres_store import PostgresEpisodicStore, SCHEMA_DDL


@pytest.mark.asyncio
async def test_record_event_sql_generation():
    store = PostgresEpisodicStore(postgres_url="postgresql://localhost/dummy")
    event = EpisodicEvent(
        session_id="sess_abc",
        turn_index=2,
        event_type=EventType.TEST_FAILURE,
        payload={"error": "ModuleNotFound"},
        outcome_status=OutcomeStatus.FAILED,
    )

    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.execute = AsyncMock()
    store._pool = mock_pool

    event_id, content_hash = await store.record_event(event)
    assert event_id == event.event_id
    assert len(content_hash) == 64
    assert mock_conn.execute.called

    call_args = mock_conn.execute.call_args[0]
    query = call_args[0]
    assert "INSERT INTO episodic_events" in query
    assert call_args[1] == event.event_id
    assert call_args[2] == "sess_abc"
    assert call_args[3] == 2
    assert call_args[6] == "test_failure"
    assert call_args[9] == "FAILED"
    assert call_args[10] == event.content_hash


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    store = PostgresEpisodicStore(postgres_url="postgresql://user:pass@localhost:5432/cortex")
    mock_pool = AsyncMock()

    with patch("asyncpg.create_pool", return_value=mock_pool) as mock_create_pool:
        await store.connect()
        mock_create_pool.assert_called_once_with("postgresql://user:pass@localhost:5432/cortex")
        assert store._pool is mock_pool

        # Connect again should be idempotent and not recreate pool
        await store.connect()
        assert mock_create_pool.call_count == 1

        await store.disconnect()
        mock_pool.close.assert_called_once()
        assert store._pool is None


@pytest.mark.asyncio
async def test_initialize_schema():
    store = PostgresEpisodicStore(postgres_url="postgresql://localhost/dummy")
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.execute = AsyncMock()
    store._pool = mock_pool

    await store.initialize_schema()
    mock_conn.execute.assert_called_once_with(SCHEMA_DDL)


@pytest.mark.asyncio
async def test_check_repetitive_loop():
    store = PostgresEpisodicStore(postgres_url="postgresql://localhost/dummy")
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetchval = AsyncMock(return_value=3)
    store._pool = mock_pool

    count = await store.check_repetitive_loop("sess_abc", "deadbeef" * 8)
    assert count == 3
    assert mock_conn.fetchval.called
    call_args = mock_conn.fetchval.call_args[0]
    assert "SELECT COUNT(*)" in call_args[0]
    assert call_args[1] == "sess_abc"
    assert call_args[2] == "deadbeef" * 8


@pytest.mark.asyncio
async def test_fetch_unconsolidated_batch():
    store = PostgresEpisodicStore(postgres_url="postgresql://localhost/dummy")
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    dummy_records = [{"event_id": uuid4()}]
    mock_conn.fetch = AsyncMock(return_value=dummy_records)
    store._pool = mock_pool

    records = await store.fetch_unconsolidated_batch(limit=10)
    assert records == dummy_records
    assert mock_conn.fetch.called
    call_args = mock_conn.fetch.call_args[0]
    assert "WHERE NOT consolidated" in call_args[0]
    assert call_args[1] == 10


@pytest.mark.asyncio
async def test_mark_consolidated():
    store = PostgresEpisodicStore(postgres_url="postgresql://localhost/dummy")
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.execute = AsyncMock()
    store._pool = mock_pool

    ids = [uuid4(), uuid4()]
    await store.mark_consolidated(ids)
    assert mock_conn.execute.called
    call_args = mock_conn.execute.call_args[0]
    assert "UPDATE episodic_events" in call_args[0]
    assert "SET consolidated = TRUE" in call_args[0]
    assert call_args[1] == ids
