import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from cortex.core.models import GraphNode, GraphRelationship
from cortex.storage.neo4j_store import Neo4jGraphStore


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    store = Neo4jGraphStore(uri="bolt://localhost:7687", user="neo4j", password="password")
    assert store._driver is None

    with patch("cortex.storage.neo4j_store.AsyncGraphDatabase.driver") as mock_driver_factory:
        mock_driver = MagicMock()
        mock_driver.close = AsyncMock()
        mock_driver_factory.return_value = mock_driver

        await store.connect()
        assert store._driver == mock_driver
        mock_driver_factory.assert_called_once_with(
            "bolt://localhost:7687", auth=("neo4j", "password")
        )

        await store.disconnect()
        mock_driver.close.assert_awaited_once()
        assert store._driver is None


@pytest.mark.asyncio
async def test_initialize_schema():
    store = Neo4jGraphStore(uri="bolt://localhost:7687", user="neo4j", password="password", embedding_dim=1536)
    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session
    store._driver = mock_driver

    await store.initialize_schema()

    # Should execute constraints and vector indexes
    assert mock_session.run.call_count == 4
    queries = [call.args[0] for call in mock_session.run.call_args_list]
    assert any("unique_code_entity" in q for q in queries)
    assert any("unique_decision" in q for q in queries)
    assert any("entity_embeddings" in q and "1536" in q for q in queries)
    assert any("decision_embeddings" in q and "1536" in q for q in queries)


@pytest.mark.asyncio
async def test_upsert_node_cypher_execution():
    store = Neo4jGraphStore(uri="bolt://localhost:7687", user="neo4j", password="password")
    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session
    store._driver = mock_driver

    node = GraphNode(
        id="src/auth/jwt.py",
        name="jwt.py",
        labels=["CodeEntity"],
        properties={"path": "src/auth/jwt.py", "language": "python"},
        embedding=[0.1] * 1536,
    )

    await store.upsert_node(node)
    assert mock_session.run.called
    call_args = mock_session.run.call_args
    cypher = call_args.args[0]
    kwargs = call_args.kwargs
    assert "MERGE (n:CodeEntity {id: $id})" in cypher
    assert kwargs["id"] == "src/auth/jwt.py"
    assert kwargs["name"] == "jwt.py"
    assert kwargs["embedding"] == [0.1] * 1536
    assert kwargs["properties"] == {"path": "src/auth/jwt.py", "language": "python"}


@pytest.mark.asyncio
async def test_upsert_node_default_label():
    store = Neo4jGraphStore(uri="bolt://localhost:7687", user="neo4j", password="password")
    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session
    store._driver = mock_driver

    node = GraphNode(
        id="root",
        name="root",
        labels=[],
        properties={},
    )

    await store.upsert_node(node)
    call_args = mock_session.run.call_args
    cypher = call_args.args[0]
    assert "MERGE (n:CodeEntity {id: $id})" in cypher


@pytest.mark.asyncio
async def test_create_bi_temporal_relationship():
    store = Neo4jGraphStore(uri="bolt://localhost:7687", user="neo4j", password="password")
    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session
    store._driver = mock_driver

    now = datetime.now(timezone.utc)
    rel = GraphRelationship(
        source_id="src/auth/jwt.py",
        target_id="src/core/security.py",
        rel_type="IMPORTS",
        valid_from=now,
        valid_to=None,
        confidence=0.95,
        properties={"syntax": "from ... import ..."},
    )

    await store.create_bi_temporal_relationship(rel)
    assert mock_session.run.called
    call_args = mock_session.run.call_args
    cypher = call_args.args[0]
    kwargs = call_args.kwargs
    assert "CREATE (from)-[r:IMPORTS" in cypher
    assert kwargs["source_id"] == "src/auth/jwt.py"
    assert kwargs["target_id"] == "src/core/security.py"
    assert kwargs["valid_from"] == now.isoformat()
    assert kwargs["valid_to"] is None
    assert kwargs["confidence"] == 0.95
    assert kwargs["properties"] == {"syntax": "from ... import ..."}


@pytest.mark.asyncio
async def test_invalidate_relationship():
    store = Neo4jGraphStore(uri="bolt://localhost:7687", user="neo4j", password="password")
    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.single.return_value = {"updated_count": 1}
    mock_session.run.return_value = mock_result
    mock_driver.session.return_value.__aenter__.return_value = mock_session
    store._driver = mock_driver

    inval_time = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    updated = await store.invalidate_relationship(
        source_id="src/auth/jwt.py",
        target_id="src/core/security.py",
        rel_type="IMPORTS",
        invalidated_at=inval_time,
    )

    assert updated == 1
    call_args = mock_session.run.call_args
    cypher = call_args.args[0]
    kwargs = call_args.kwargs
    assert "MATCH (from {id: $source_id})-[r:IMPORTS]->(to {id: $target_id})" in cypher
    assert "WHERE r.valid_to IS NULL" in cypher
    assert kwargs["invalid_time"] == inval_time.isoformat()


@pytest.mark.asyncio
async def test_vector_search():
    store = Neo4jGraphStore(uri="bolt://localhost:7687", user="neo4j", password="password")
    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data.return_value = [
        {"id": "src/auth/jwt.py", "name": "jwt.py", "labels": ["CodeEntity"], "score": 0.92}
    ]
    mock_session.run.return_value = mock_result
    mock_driver.session.return_value.__aenter__.return_value = mock_session
    store._driver = mock_driver

    query_embedding = [0.1] * 1536
    results = await store.vector_search(query_embedding, top_k=5)

    assert len(results) == 1
    assert results[0]["id"] == "src/auth/jwt.py"
    call_args = mock_session.run.call_args
    cypher = call_args.args[0]
    kwargs = call_args.kwargs
    assert "CALL db.index.vector.queryNodes('entity_embeddings', $top_k, $embedding)" in cypher
    assert kwargs["top_k"] == 5
    assert kwargs["embedding"] == query_embedding


@pytest.mark.asyncio
async def test_traverse_dependencies():
    store = Neo4jGraphStore(uri="bolt://localhost:7687", user="neo4j", password="password")
    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data.return_value = [
        {"id": "src/core/security.py", "name": "security.py", "labels": ["CodeEntity"], "depth": 1}
    ]
    mock_session.run.return_value = mock_result
    mock_driver.session.return_value.__aenter__.return_value = mock_session
    store._driver = mock_driver

    now = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    results = await store.traverse_dependencies(
        entity_id="src/auth/jwt.py",
        temporal_point=now,
        max_depth=3,
    )

    assert len(results) == 1
    assert results[0]["name"] == "security.py"
    call_args = mock_session.run.call_args
    cypher = call_args.args[0]
    kwargs = call_args.kwargs
    assert "r*1..3" in cypher
    assert kwargs["entity_id"] == "src/auth/jwt.py"
    assert kwargs["t_check"] == now.isoformat()


@pytest.mark.asyncio
async def test_unconnected_driver_raises():
    store = Neo4jGraphStore(uri="bolt://localhost:7687", user="neo4j", password="password")
    with pytest.raises(AssertionError):
        await store.initialize_schema()
