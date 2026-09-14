import pytest
from cortex.config import CortexConfig


def test_default_config():
    config = CortexConfig(
        postgres_url="postgresql://cortex:secret@localhost:5432/cortex_memory",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="password",
    )
    assert config.postgres_url == "postgresql://cortex:secret@localhost:5432/cortex_memory"
    assert config.neo4j_uri == "bolt://localhost:7687"
    assert config.working_memory_token_cap == 4000
    assert config.context_budget_ceiling == 2500
