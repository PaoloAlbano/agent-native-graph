"""Run a bounded, paginated ANA workflow without a model or benchmark dataset."""

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx


@contextmanager
def workflow(client: httpx.Client) -> Iterator[dict[str, str]]:
    """Keep the workflow token out of URLs and close it even when a tool fails."""
    response = client.post("/sessions")
    response.raise_for_status()
    headers = {"X-ANA-Session": response.json()["session_id"]}
    failed = False
    try:
        yield headers
    except BaseException:
        failed = True
        raise
    finally:
        try:
            closed = client.delete("/sessions/current", headers=headers)
            if closed.status_code != 404:
                closed.raise_for_status()
        except httpx.HTTPError:
            if not failed:
                raise
            print(
                "Workflow cleanup failed; the server idle timeout remains active.", file=sys.stderr
            )


def run_demo(
    client: httpx.Client,
    *,
    label: str | None = None,
    page_size: int = 10,
    scan_limit: int = 25,
    emit: Callable[[dict], None] = lambda value: print(json.dumps(value, ensure_ascii=True)),
) -> dict:
    """Discover tools/schema, scan a small label sample and fetch every stored page."""
    if page_size < 1 or not 1 <= scan_limit <= 5000:
        raise ValueError("page_size must be positive; scan_limit must be between 1 and 5000")
    response = client.get("/tools/specs")
    response.raise_for_status()
    names = {spec["function"]["name"] for spec in response.json()["tools"]}
    if not {"schema_overview", "node_scan", "fetch"} <= names:
        raise ValueError("This example needs schema_overview, node_scan and fetch in the catalog")
    with workflow(client) as headers:

        def call(tool: str, args: dict) -> dict:
            response = client.post(
                "/tools/call", headers=headers, json={"tool": tool, "args": args}
            )
            response.raise_for_status()
            return response.json()["result"]

        overview = call("schema_overview", {})
        if label is None:
            labels = overview.get("labels", [])
            if not labels:
                result = {"label": None, "pages": 0, "rows": 0, "message": "No labels discovered"}
                emit(result)
                return result
            label = labels[0]["label"]
        sampled = call("node_scan", {"label": label, "limit": scan_limit})
        handle = sampled["handle"]
        offset, pages, row_count = 0, 0, 0
        while True:
            page = call("fetch", {"from": handle, "offset": offset, "limit": page_size})
            if page.get("contract_version") != "ana-fetch-v1":
                raise ValueError("Expected ana-fetch-v1; update the client for this server")
            emit({"page": pages + 1, "columns": page["columns"], "rows": page["rows"]})
            pages += 1
            row_count += len(page["rows"])
            next_offset = page["next_offset"]
            if next_offset is None:
                break
            if not isinstance(next_offset, int) or next_offset <= offset:
                raise ValueError("Server returned a non-advancing pagination offset")
            offset = next_offset
        summary = {
            "label": label,
            "pages": pages,
            "rows": row_count,
            "scan_limit": scan_limit,
            "scope": "All pages of a bounded sample handle, not the entire graph",
        }
        emit(summary)
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--label", help="Optional existing label; otherwise use the first discovered label"
    )
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--scan-limit", type=int, default=25)
    args = parser.parse_args()
    key = os.getenv("ANA_API_KEY")
    try:
        if not key and os.getenv("ANA_API_KEY_FILE"):
            key = Path(os.environ["ANA_API_KEY_FILE"]).read_text(encoding="utf-8").strip()
        if not key:
            raise ValueError(
                "Set ANA_API_KEY or ANA_API_KEY_FILE; do not pass credentials in the URL"
            )
        with httpx.Client(
            base_url=args.url,
            headers={"Authorization": f"Bearer {key}"},
            timeout=120,
            follow_redirects=False,
        ) as client:
            run_demo(client, label=args.label, page_size=args.page_size, scan_limit=args.scan_limit)
    except httpx.HTTPStatusError as exc:
        raise SystemExit(
            f"HTTP {exc.response.status_code}; check credentials, permissions and session/server state"
        ) from None
    except httpx.TransportError:
        raise SystemExit("HTTP connection failed; check the server URL and connectivity") from None
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
