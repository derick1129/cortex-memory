"""Neo4j Knowledge Graph and Native Vector Store implementation for Cortex Memory."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from neo4j import AsyncDriver, AsyncGraphDatabase

from cortex.core.models import GraphNode, GraphRelationship


class Neo4jGraphStore:
    """Tier 3 (Vector) & Tier 4 (Knowledge Graph) Neo4j Storage Engine."""

    def __init__(self, uri: str, user: str, password: str, embedding_dim: int = 1536) -> None:
        self.uri = uri
        self.user = user
        self.password = password
        self.embedding_dim = embedding_dim
        self._driver: Optional[AsyncDriver] = None

    async def connect(self) -> None:
        """Connect to the Neo4j instance using the async driver."""
        if not self._driver:
            self._driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))

    async def disconnect(self) -> None:
        """Disconnect and close the driver."""
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def initialize_schema(self) -> None:
        """Initialize uniqueness constraints and vector indexes."""
        assert self._driver is not None, "Neo4j driver is not connected."
        queries = [
            "CREATE CONSTRAINT unique_code_entity IF NOT EXISTS FOR (e:CodeEntity) REQUIRE e.id IS UNIQUE;",
            "CREATE CONSTRAINT unique_decision IF NOT EXISTS FOR (d:ArchitecturalDecision) REQUIRE d.id IS UNIQUE;",
            f"""
            CREATE VECTOR INDEX entity_embeddings IF NOT EXISTS
            FOR (e:CodeEntity) ON (e.embedding)
            OPTIONS {{indexConfig: {{
              `vector.dimensions`: {self.embedding_dim},
              `vector.similarity_function`: 'cosine'
            }}}};
            """,
            f"""
            CREATE VECTOR INDEX decision_embeddings IF NOT EXISTS
            FOR (d:ArchitecturalDecision) ON (d.embedding)
            OPTIONS {{indexConfig: {{
              `vector.dimensions`: {self.embedding_dim},
              `vector.similarity_function`: 'cosine'
            }}}};
            """,
        ]
        async with self._driver.session() as session:
            for q in queries:
                await session.run(q)

    async def upsert_node(self, node: GraphNode) -> None:
        """Upsert a code or architectural node with its metadata and embedding."""
        assert self._driver is not None, "Neo4j driver is not connected."
        primary_label = node.labels[0] if node.labels else "CodeEntity"
        cypher = f"""
        MERGE (n:{primary_label} {{id: $id}})
        SET n.name = $name,
            n.embedding = $embedding,
            n += $properties
        """
        async with self._driver.session() as session:
            await session.run(
                cypher,
                id=node.id,
                name=node.name,
                embedding=node.embedding,
                properties=node.properties,
            )

    async def create_bi_temporal_relationship(self, rel: GraphRelationship) -> None:
        """Create a directed bi-temporal relationship with confidence score."""
        assert self._driver is not None, "Neo4j driver is not connected."
        cypher = f"""
        MATCH (from {{id: $source_id}}), (to {{id: $target_id}})
        CREATE (from)-[r:{rel.rel_type} {{
            valid_from: $valid_from,
            valid_to: $valid_to,
            confidence: $confidence
        }}]->(to)
        SET r += $properties
        """
        async with self._driver.session() as session:
            await session.run(
                cypher,
                source_id=rel.source_id,
                target_id=rel.target_id,
                valid_from=rel.valid_from.isoformat(),
                valid_to=rel.valid_to.isoformat() if rel.valid_to else None,
                confidence=rel.confidence,
                properties=rel.properties,
            )

    async def invalidate_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        invalidated_at: Optional[datetime] = None,
    ) -> int:
        """Invalidate an active relationship by setting its valid_to timestamp."""
        assert self._driver is not None, "Neo4j driver is not connected."
        invalid_time = (invalidated_at or datetime.now(timezone.utc)).isoformat()
        cypher = f"""
        MATCH (from {{id: $source_id}})-[r:{rel_type}]->(to {{id: $target_id}})
        WHERE r.valid_to IS NULL
        SET r.valid_to = $invalid_time
        RETURN count(r) AS updated_count
        """
        async with self._driver.session() as session:
            result = await session.run(
                cypher,
                source_id=source_id,
                target_id=target_id,
                invalid_time=invalid_time,
            )
            record = await result.single()
            return int(record["updated_count"] if record else 0)

    async def vector_search(self, embedding: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        """Perform cosine similarity search on code entity vector embeddings."""
        assert self._driver is not None, "Neo4j driver is not connected."
        cypher = """
        CALL db.index.vector.queryNodes('entity_embeddings', $top_k, $embedding)
        YIELD node, score
        RETURN node.id AS id, node.name AS name, labels(node) AS labels, score
        ORDER BY score DESC
        """
        async with self._driver.session() as session:
            result = await session.run(cypher, top_k=top_k, embedding=embedding)
            records = await result.data()
            return records

    async def traverse_dependencies(
        self,
        entity_id: str,
        temporal_point: Optional[datetime] = None,
        max_depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """Traverse relationship paths bounded by bi-temporal validity."""
        assert self._driver is not None, "Neo4j driver is not connected."
        t_check = (temporal_point or datetime.now(timezone.utc)).isoformat()
        cypher = f"""
        MATCH path = (root {{id: $entity_id}})-[r*1..{max_depth}]-(neighbor)
        WHERE ALL(rel IN r WHERE rel.valid_from <= $t_check AND (rel.valid_to IS NULL OR rel.valid_to > $t_check))
        RETURN neighbor.id AS id, neighbor.name AS name, labels(neighbor) AS labels, length(path) AS depth
        LIMIT 25
        """
        async with self._driver.session() as session:
            result = await session.run(cypher, entity_id=entity_id, t_check=t_check)
            return await result.data()
