"""Neo4j-specific connection settings; never part of the generic backend contract."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str = field(default="bolt://127.0.0.1:7687", repr=False)
    user: str = "neo4j"
    password: str = field(default="password", repr=False)
    database: str | None = None
    query_timeout_s: int | None = 30
    identity_mode: str = "property"
    workflow_timeout_s: int = 30

    def __post_init__(self) -> None:
        if self.identity_mode not in {"property", "transaction"}:
            raise ValueError("identity_mode must be property or transaction")
        if type(self.workflow_timeout_s) is not int or self.workflow_timeout_s <= 0:
            raise ValueError("workflow_timeout_s must be a positive integer")
        if self.database is not None and (
            not isinstance(self.database, str) or not self.database.strip()
        ):
            raise ValueError("database must be a nonempty string or None")
        if self.query_timeout_s is not None and (
            type(self.query_timeout_s) is not int or self.query_timeout_s <= 0
        ):
            raise ValueError("query_timeout_s must be a positive integer or None")

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        """Read settings once; applications keep this immutable snapshot."""
        return cls(
            uri=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "password"),
            database=os.getenv("NEO4J_DATABASE") or None,
            query_timeout_s=int(os.getenv("ANA_NEO4J_QUERY_TIMEOUT_S", "30")),
            identity_mode=os.getenv("ANA_NEO4J_IDENTITY_MODE", "property"),
            workflow_timeout_s=int(os.getenv("ANA_NEO4J_WORKFLOW_TIMEOUT_S", "30")),
        )
