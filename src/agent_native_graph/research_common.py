import argparse
import json
import os
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from neo4j.graph import Node, Relationship
from neo4j.graph import Path as Neo4jPath

from agent_native_graph.llm_providers.openai_compatible import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    ChatClient,
)

__all__ = [
    "ChatClient",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_NEO4J_PASSWORD",
    "DEFAULT_NEO4J_URI",
    "DEFAULT_NEO4J_USER",
    "Neo4jRunner",
    "QueryExecution",
    "add_llm_args",
    "add_neo4j_args",
    "append_jsonl",
    "completed_qids",
    "extract_cypher",
    "limited_tasks",
    "normalize_answer_rows",
    "normalize_result_rows",
    "parse_answer_json",
    "read_jsonl",
    "result_matches_answer",
    "write_jsonl",
]

DEFAULT_NEO4J_URI = "bolt://127.0.0.1:7687"
DEFAULT_NEO4J_USER = "neo4j"
DEFAULT_NEO4J_PASSWORD = "password"


def add_neo4j_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", DEFAULT_NEO4J_URI))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", DEFAULT_NEO4J_USER))
    parser.add_argument(
        "--neo4j-password",
        default=os.getenv("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD),
    )
    parser.add_argument("--query-timeout-s", type=float, default=60.0)


def add_llm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.getenv("MODEL", DEFAULT_MODEL))
    parser.add_argument("--api-key-env", default="API_KEY")
    parser.add_argument("--api-key-file", type=Path, default=_default_api_key_file())
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument(
        "--thinking-effort",
        choices=["low", "medium", "high"],
        help=(
            "Optional reasoning/thinking effort hint. Sent both as "
            "chat_template_kwargs.thinking_effort and reasoning_effort for "
            "OpenAI-compatible gateways that support it."
        ),
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=16000)


def _default_api_key_file() -> Path | None:
    path = os.getenv("API_KEY_FILE")
    return Path(path) if path else None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parse_answer_json(value: object) -> list[list[Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    if not isinstance(parsed, list):
        return [[parsed]]
    return [list(item) if isinstance(item, list | tuple) else [item] for item in parsed]


def normalize_result_rows(
    rows: Sequence[Mapping[str, Any]] | Sequence[Sequence[Any]],
) -> list[list[Any]]:
    normalized: list[list[Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            normalized.append([_normalize_value(value) for value in row.values()])
        else:
            normalized.append([_normalize_value(value) for value in row])
    return normalized


def normalize_answer_rows(rows: Sequence[Sequence[Any]]) -> list[list[Any]]:
    return [[_normalize_value(value) for value in row] for row in rows]


def result_matches_answer(
    actual: Sequence[Sequence[Any]], expected: Sequence[Sequence[Any]]
) -> bool:
    return _sort_rows(actual) == _sort_rows(expected)


def _sort_rows(rows: Sequence[Sequence[Any]]) -> list[str]:
    return sorted(json.dumps(list(row), ensure_ascii=False, sort_keys=True) for row in rows)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Node):
        return {
            "id": value.element_id,
            "labels": sorted(value.labels),
            "properties": {str(key): _normalize_value(item) for key, item in dict(value).items()},
        }
    if isinstance(value, Relationship):
        return {
            "id": value.element_id,
            "type": value.type,
            "start": value.start_node.element_id,
            "end": value.end_node.element_id,
            "properties": {str(key): _normalize_value(item) for key, item in dict(value).items()},
        }
    if isinstance(value, Neo4jPath):
        return {
            "nodes": [_normalize_value(node) for node in value.nodes],
            "relationships": [_normalize_value(rel) for rel in value.relationships],
        }
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    return value


def extract_cypher(text: str) -> str:
    fenced = re.search(r"```(?:cypher)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip().rstrip(";")
    stripped = text.strip()
    for marker in ("MATCH ", "CALL ", "WITH ", "RETURN "):
        index = stripped.upper().find(marker)
        if index >= 0:
            return stripped[index:].strip().rstrip(";")
    return stripped.rstrip(";")


@dataclass(frozen=True, slots=True)
class QueryExecution:
    ok: bool
    rows: list[list[Any]]
    columns: list[str]
    elapsed_s: float
    error: str | None = None


class Neo4jRunner:
    def __init__(self, uri: str, user: str, password: str, timeout_s: float = 60.0) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._timeout_s = timeout_s

    def close(self) -> None:
        self._driver.close()

    def execute(self, query: str) -> QueryExecution:
        started = time.perf_counter()
        try:
            with self._driver.session() as session:
                result = session.run(query, timeout=self._timeout_s)
                keys = list(result.keys())
                rows = [[_normalize_value(record.get(key)) for key in keys] for record in result]
            return QueryExecution(
                ok=True,
                rows=rows,
                columns=keys,
                elapsed_s=time.perf_counter() - started,
            )
        except (Neo4jError, ValueError) as exc:
            return QueryExecution(
                ok=False,
                rows=[],
                columns=[],
                elapsed_s=time.perf_counter() - started,
                error=f"{exc.__class__.__name__}: {exc}",
            )


def completed_qids(path: Path) -> set[object]:
    if not path.exists():
        return set()
    qids: set[object] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                qids.add(json.loads(line).get("qid"))
    return qids


def limited_tasks(tasks: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None:
        return tasks
    return tasks[:limit]
