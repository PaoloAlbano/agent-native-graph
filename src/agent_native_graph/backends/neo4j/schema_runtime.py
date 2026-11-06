"""Neo4j sampling queries and compatibility exports for schema helpers."""

from typing import Any

from agent_native_graph.core.graph_utils import _safe_name, _tool_value
from agent_native_graph.core.schema_runtime import (
    inspect_paths as inspect_paths,
)
from agent_native_graph.core.schema_runtime import (
    node_property_affordances as node_property_affordances,
)
from agent_native_graph.core.schema_runtime import (
    schema_affordance as schema_affordance,
)
from agent_native_graph.core.schema_runtime import (
    schema_describe_label as schema_describe_label,
)
from agent_native_graph.core.schema_runtime import (
    schema_describe_relationship as schema_describe_relationship,
)
from agent_native_graph.core.schema_runtime import (
    schema_get as schema_get,
)
from agent_native_graph.core.schema_runtime import (
    schema_inspect as schema_inspect,
)
from agent_native_graph.core.schema_runtime import (
    schema_overview as schema_overview,
)
from agent_native_graph.core.schema_runtime import (
    schema_score as schema_score,
)
from agent_native_graph.core.schema_runtime import (
    schema_search as schema_search,
)


def node_property_samples(backend, label: str, prop: str, *, limit: int = 3) -> list[Any]:
    if not hasattr(backend, "_driver"):
        return []
    safe_label = _safe_name(label)
    safe_prop = _safe_name(prop)
    query = (
        f"MATCH (n:`{safe_label}`) "
        f"WHERE n.`{safe_prop}` IS NOT NULL "
        f"RETURN n.`{safe_prop}` AS value LIMIT $limit"
    )
    try:
        with backend._driver.session() as session:
            return [
                _tool_value(record["value"]) for record in backend._run(session, query, limit=limit)
            ]
    except Exception:
        return []


def relationship_property_samples(
    backend, rel_type: str, prop: str, *, limit: int = 3
) -> list[Any]:
    if not hasattr(backend, "_driver"):
        return []
    safe_rel = _safe_name(rel_type)
    safe_prop = _safe_name(prop)
    query = (
        f"MATCH ()-[r:`{safe_rel}`]->() "
        f"WHERE r.`{safe_prop}` IS NOT NULL "
        f"RETURN r.`{safe_prop}` AS value LIMIT $limit"
    )
    try:
        with backend._driver.session() as session:
            return [
                _tool_value(record["value"]) for record in backend._run(session, query, limit=limit)
            ]
    except Exception:
        return []
