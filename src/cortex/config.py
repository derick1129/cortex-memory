from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CortexConfig(BaseSettings):
    postgres_url: str = Field(default="postgresql://cortex:cortex_secure_password@localhost:5432/cortex_memory")
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="cortex_secure_password")
    working_memory_token_cap: int = Field(default=4000)
    context_budget_ceiling: int = Field(default=2500)
    rrf_k: int = Field(default=60)
    weight_vector: float = Field(default=1.0)
    weight_graph: float = Field(default=1.2)
    weight_episodic: float = Field(default=0.8)
    llm_model: str = Field(default="claude-3-5-haiku-20241022")
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")
    embedding_dimension: int = Field(default=1536)

    model_config = SettingsConfigDict(
        env_prefix="CORTEX_",
        env_file=".env",
        extra="ignore",
    )
