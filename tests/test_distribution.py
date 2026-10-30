"""Opt-in wheel/container smoke on disposable Docker resources, never Company.

Run make test-distribution. No LLM or reference repository is used.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    os.environ.get("ANA_TEST_DISTRIBUTION") != "1",
    reason="Set ANA_TEST_DISTRIBUTION=1 for disposable Docker/wheel integration",
)


def clean_environment():
    """Pass only process/bootstrap settings, never inherited provider/graph secrets."""
    allowed = {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "UV_CACHE_DIR",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def run(*args, cwd, env=None, timeout=300):
    """Bound subprocess lifetime and retain useful diagnostics on test failures."""
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, f"{args[0]} failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout.strip()


def wait_for(probe, description, timeout=120):
    """Poll readiness of only the resources created by this fixture."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if probe():
                return
        except Exception:
            pass
        time.sleep(1)
    raise AssertionError(f"Timed out waiting for {description}")


@pytest.fixture(scope="module")
def distribution(tmp_path_factory):
    """Build/install once and own all newly created Docker resources until teardown."""
    work = tmp_path_factory.mktemp("ana-distribution")
    env = clean_environment()
    for executable in ("docker", "uv"):
        assert shutil.which(executable), f"{executable} is required for this opt-in test"
    run("docker", "info", cwd=work, timeout=30)
    tag = "ana-dist-" + uuid4().hex[:12]
    network, graph, service = tag, tag + "-graph", tag + "-service"
    service_image = os.getenv("ANA_TEST_SERVICE_IMAGE") or tag + ":test"
    graph_image = os.getenv("ANA_TEST_NEO4J_IMAGE", "neo4j:2026.05.0")
    created, image_built, network_created = [], False, False
    try:
        dist = (
            Path(os.environ["ANA_TEST_DIST_DIR"]).resolve()
            if os.getenv("ANA_TEST_DIST_DIR")
            else work / "dist"
        )
        if not os.getenv("ANA_TEST_DIST_DIR"):
            run("uv", "build", "--wheel", "--out-dir", str(dist), cwd=ROOT, env=env)
        wheels = list(dist.glob("*.whl"))
        assert len(wheels) == 1
        run("uv", "venv", "--python", sys.executable, str(work / "venv"), cwd=work, env=env)
        python = str(work / "venv/bin/python")
        run("uv", "pip", "install", "--python", python, str(wheels[0]), cwd=work, env=env)
        shutil.copyfile(ROOT / "tests/distribution_workflow.py", work / "client.py")
        if not os.getenv("ANA_TEST_SERVICE_IMAGE"):
            run(
                "docker",
                "buildx",
                "build",
                "--load",
                "--build-context",
                f"wheels={dist}",
                "--tag",
                service_image,
                str(ROOT),
                cwd=work,
                timeout=900,
            )
            image_built = True
        run("docker", "network", "create", network, cwd=work)
        network_created = True
        created.append(graph)
        run(
            "docker",
            "run",
            "--detach",
            "--name",
            graph,
            "--network",
            network,
            "--network-alias",
            "graph",
            "--publish",
            "127.0.0.1::7687",
            "--memory",
            "1g",
            "--cpus",
            "2",
            "--tmpfs",
            "/data",
            "--env",
            "NEO4J_AUTH=neo4j/ana-disposable-test",
            "--env",
            "NEO4J_server_memory_heap_initial__size=256m",
            "--env",
            "NEO4J_server_memory_heap_max__size=256m",
            "--env",
            "NEO4J_server_memory_pagecache_size=128m",
            graph_image,
            cwd=work,
        )
        port = run("docker", "port", graph, "7687/tcp", cwd=work).rsplit(":", 1)[1]
        uri = f"bolt://127.0.0.1:{port}"
        with GraphDatabase.driver(
            uri, auth=("neo4j", "ana-disposable-test"), connection_timeout=2
        ) as driver:
            wait_for(lambda: driver.verify_connectivity() is None, "disposable Neo4j")
            with driver.session(database="neo4j") as session:
                session.run(
                    "UNWIND range(0, 1) AS i CREATE (:Zone {id: 'z' + toString(i), zone_key: 'zone-' + toString(i)})"
                ).consume()
                session.run(
                    "UNWIND range(0, 24) AS i MATCH (z:Zone {id: 'z' + toString(i % 2)}) "
                    "CREATE (d:Device:Sensor {id: 'd' + toString(i), device_key: 'device-' + CASE WHEN i < 10 THEN '0' ELSE '' END + toString(i), "
                    "tags: ['lab', 'temperature'], installed_on: date('2024-01-02'), reading: CASE WHEN i = 0 THEN null ELSE i * 1.5 END}) "
                    "CREATE (d)-[:LOCATED_IN {since: 2024}]->(z)"
                ).consume()
                session.run(
                    "CREATE (u:Unkeyed {display_name: 'no identifier'}) WITH u MATCH (z:Zone {id: 'z0'}) CREATE (u)-[:LOCATED_IN]->(z)"
                ).consume()
                session.run(
                    "UNWIND ['a', 'b', 'c'] AS marker "
                    "CREATE (p:Probe {marker: marker, id: CASE WHEN marker = 'c' THEN null ELSE 'duplicate' END}) "
                    "CREATE (t:Endpoint {marker: toUpper(marker)}) CREATE (p)-[:POINTS_TO]->(t)"
                ).consume()
                session.run(
                    "CREATE (:Twin {id: 'same', marker: 'identical'}), "
                    "(:Twin {id: 'same', marker: 'identical'}), (:Tombstone {id: 'replaceable', marker: 'old'})"
                ).consume()
                session.run(
                    "CREATE (:UnkeyedTwin {marker: 'identical'}), (:UnkeyedTwin {marker: 'identical'})"
                ).consume()
        auth = work / "auth.config.json"
        auth.write_text(
            json.dumps(
                {
                    "clients": [
                        {"id": name, "api_key": secrets.token_urlsafe(32)}
                        for name in ("reader-a", "reader-b")
                    ]
                }
            )
        )
        auth.chmod(0o644)  # Read-only bind mount must be readable by container UID 10001.
        yield {
            "work": work,
            "env": env,
            "python": python,
            "uri": uri,
            "auth": auth,
            "network": network,
            "service": service,
            "image": service_image,
            "created": created,
        }
    finally:
        for name in reversed(created):
            subprocess.run(
                ["docker", "rm", "--force", "--volumes", name], capture_output=True, timeout=60
            )
        if network_created:
            subprocess.run(["docker", "network", "rm", network], capture_output=True, timeout=30)
        if image_built:
            subprocess.run(
                ["docker", "image", "rm", service_image], capture_output=True, timeout=60
            )


def test_installed_wheel_without_checkout_data_or_llm(distribution):
    state = distribution
    report = json.loads(
        run(
            state["python"],
            "-I",
            "client.py",
            "library",
            cwd=state["work"],
            env=state["env"] | {"ANA_TEST_GRAPH_URI": state["uri"]},
        )
    )
    assert report == {
        "device_count": 25,
        "page_sizes": [7, 7, 7, 4],
        "traversed_rows": 25,
        "wheel_import": True,
        "isolated_workflows": True,
        "close_on_error": True,
    }


def test_transaction_identity_from_installed_wheel(distribution):
    state = distribution
    report = json.loads(
        run(
            state["python"],
            "-I",
            "client.py",
            "identity",
            cwd=state["work"],
            env=state["env"] | {"ANA_TEST_GRAPH_URI": state["uri"]},
        )
    )
    assert all(report.values()) and report["deleted_node_invalidates"]
    assert report["distinct_rows_with_duplicate_ids"] and report["distinct_rows_without_ids"]


def test_finalization_from_installed_wheel_without_model_calls(distribution):
    state = distribution
    report = json.loads(
        run(
            state["python"],
            "-I",
            "client.py",
            "finalization",
            cwd=state["work"],
            env=state["env"] | {"ANA_TEST_GRAPH_URI": state["uri"]},
        )
    )
    assert report == {
        "packaged_runner": True,
        "explicit_fetch_required": True,
        "recovery_with_explicit_fetch": True,
        "legacy_fallbacks_preserved": True,
    }


@pytest.mark.parametrize("identity_mode", ["property", "transaction"])
def test_shipped_docker_service_on_the_same_generic_graph(distribution, identity_mode):
    state = dict(distribution)
    state["service"] += "-" + identity_mode
    state["created"].append(state["service"])
    run(
        "docker",
        "run",
        "--detach",
        "--name",
        state["service"],
        "--network",
        state["network"],
        "--publish",
        "127.0.0.1::8080",
        "--env",
        "NEO4J_URI=bolt://graph:7687",
        "--env",
        "NEO4J_USER=neo4j",
        "--env",
        "NEO4J_PASSWORD=ana-disposable-test",
        "--env",
        "NEO4J_DATABASE=neo4j",
        "--env",
        "ANA_MAX_SESSIONS=2",
        "--env",
        f"ANA_NEO4J_IDENTITY_MODE={identity_mode}",
        "--env",
        "ANA_AUTH_FILE=/run/ana/auth.json",
        "--volume",
        f"{state['auth']}:/run/ana/auth.json:ro",
        "--volume",
        f"{state['work'] / 'client.py'}:/run/ana/client.py:ro",
        state["image"],
        cwd=state["work"],
    )
    port = run("docker", "port", state["service"], "8080/tcp", cwd=state["work"]).rsplit(":", 1)[1]
    url = f"http://127.0.0.1:{port}"
    wait_for(lambda: httpx.get(url + "/health", timeout=2).status_code == 200, "ANA HTTP service")
    assert run("docker", "exec", state["service"], "id", "-u", cwd=state["work"]) == "10001"
    report = json.loads(
        run(
            state["python"],
            "-I",
            "client.py",
            "identity-http" if identity_mode == "transaction" else "http",
            cwd=state["work"],
            env=state["env"]
            | {"ANA_TEST_AUTH_FILE": str(state["auth"]), "ANA_TEST_SERVICE_URL": url},
        )
    )
    if identity_mode == "transaction":
        assert all(report.values()) and report["opaque_identity"]
        assert report["distinct_rows_with_duplicate_ids"] and report["distinct_rows_without_ids"]
    else:
        assert report == {
            "device_count": 25,
            "page_sizes": [7, 7, 7, 4],
            "traversed_rows": 25,
            "authenticated_http": True,
            "isolated_sessions": True,
            "capacity_released": True,
        }
        finalization = json.loads(
            run(
                "docker",
                "exec",
                "--env",
                "ANA_TEST_GRAPH_URI=bolt://graph:7687",
                "--env",
                "ANA_TEST_PACKAGE_ROOT=/app/.venv",
                state["service"],
                "python",
                "-I",
                "/run/ana/client.py",
                "finalization",
                cwd=state["work"],
            )
        )
        assert finalization == {
            "packaged_runner": True,
            "explicit_fetch_required": True,
            "recovery_with_explicit_fetch": True,
            "legacy_fallbacks_preserved": True,
        }
    run("docker", "stop", "--time", "15", state["service"], cwd=state["work"])
    assert (
        run(
            "docker",
            "inspect",
            "--format",
            "{{.State.ExitCode}}",
            state["service"],
            cwd=state["work"],
        )
        == "0"
    )
