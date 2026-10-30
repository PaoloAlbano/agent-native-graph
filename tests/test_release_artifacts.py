"""Offline release gates: version identity, package inventory and publish boundaries."""

import hashlib
import io
import runpy
import tarfile
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HELPERS = runpy.run_path(str(ROOT / ".github/release_artifacts.py"))


@pytest.fixture
def package(tmp_path):
    """Small real archives exercise the audit without building or downloading packages."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="agent-native-graph"\nversion="0.1.0"\n'
    )
    (tmp_path / "uv.lock").write_text('[[package]]\nname="agent-native-graph"\nversion="0.1.0"\n')
    profiles = tmp_path / "src/agent_native_graph/profiles"
    profiles.mkdir(parents=True)
    (profiles / "temp0-none.yaml").write_text("temperature: 0\n")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / ".gitignore").write_text("*\n")
    wheel = dist / "agent_native_graph-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name in ("__init__.py", "interfaces/cli.py", "profiles/temp0-none.yaml"):
            archive.writestr("agent_native_graph/" + name, "")
        archive.writestr(
            "agent_native_graph-0.1.0.dist-info/METADATA",
            "Name: agent-native-graph\nVersion: 0.1.0\n",
        )
    source = dist / "agent_native_graph-0.1.0.tar.gz"
    write_source(source)
    return tmp_path, dist, wheel, source


def write_source(path, extra=()):
    """Construct a source archive, optionally inserting deliberately forbidden paths."""
    with tarfile.open(path, "w:gz") as archive:
        for name in (
            "pyproject.toml",
            "uv.lock",
            "README.md",
            "LICENSE",
            "src/agent_native_graph/__init__.py",
            *extra,
        ):
            info = tarfile.TarInfo("agent_native_graph-0.1.0/" + name)
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))


def test_valid_distributions_get_reproducible_checksums(package):
    root, dist, wheel, source = package
    assert HELPERS["validate_version"](root, "v0.1.0") == "0.1.0"
    HELPERS["validate_artifacts"](root, dist, "0.1.0")
    expected = "".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in (wheel, source)
    )
    assert (dist / "SHA256SUMS").read_text() == expected
    HELPERS["validate_artifacts"](root, dist, "0.1.0")
    assert (dist / "SHA256SUMS").read_text() == expected


@pytest.mark.parametrize("tag", ["0.1.0", "v0.2.0", "v0.1.0rc1", "v0.1.0; echo bad"])
def test_reject_invalid_or_mismatched_tag(package, tag):
    with pytest.raises(ValueError, match="stable release tag"):
        HELPERS["validate_version"](package[0], tag)


def test_reject_stale_lock(package):
    root = package[0]
    (root / "uv.lock").write_text('[[package]]\nname="agent-native-graph"\nversion="0.0.1"\n')
    with pytest.raises(ValueError, match="uv.lock"):
        HELPERS["validate_version"](root, "v0.1.0")


@pytest.mark.parametrize(
    "member",
    [
        "results/run.jsonl",
        ".env",
        "agent_native_graph/../secret",
        "agent_native_graph/__pycache__/x.pyc",
    ],
)
def test_reject_unexpected_wheel_contents(package, member):
    root, dist, wheel, _ = package
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr(member, "not for release")
    with pytest.raises(ValueError, match="Unexpected wheel member"):
        HELPERS["validate_artifacts"](root, dist, "0.1.0")


@pytest.mark.parametrize(
    "member", ["results/run.jsonl", ".env", "../secret", "src/agent_native_graph/.secret"]
)
def test_reject_unexpected_source_contents(package, member):
    root, dist, _, source = package
    write_source(source, [member])
    with pytest.raises(ValueError, match="Unexpected sdist member"):
        HELPERS["validate_artifacts"](root, dist, "0.1.0")


def test_missing_profile_is_an_error(package):
    root, dist, _, _ = package
    (root / "src/agent_native_graph/profiles/new.yaml").write_text("temperature: 1\n")
    with pytest.raises(ValueError, match="bundled YAML profiles"):
        HELPERS["validate_artifacts"](root, dist, "0.1.0")


def test_unrelated_artifact_is_an_error(package):
    root, dist, _, _ = package
    (dist / "old.whl").write_bytes(b"stale artifact")
    with pytest.raises(ValueError, match="exactly one"):
        HELPERS["validate_artifacts"](root, dist, "0.1.0")


def test_manual_workflow_cannot_publish_and_release_reuses_tested_artifacts():
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    build, publish = workflow["jobs"]["build"], workflow["jobs"]["publish"]
    assert workflow["permissions"] == {"contents": "read"}
    assert publish["if"] == "github.event_name == 'release' && !github.event.release.prerelease"
    assert publish["needs"] == "build"
    assert publish["permissions"] == {"contents": "write", "packages": "write"}
    steps = build["steps"]
    distribution = next(s for s in steps if s.get("run") == "make test-distribution")
    assert distribution["env"]["ANA_TEST_SERVICE_IMAGE"] == "ana-release:test"
    assert distribution["env"]["ANA_TEST_DIST_DIR"] == "${{ github.workspace }}/dist"
    build_commands = "\n".join(s.get("run", "") for s in steps)
    publish_commands = "\n".join(s.get("run", "") for s in publish["steps"])
    assert "--build-context wheels=./dist" in build_commands
    assert "docker save ana-release:test" in build_commands
    assert "docker load --input image.tar.gz" in publish_commands
    assert "docker build" not in publish_commands
    assert "uv build" not in publish_commands
    assert "--clobber" not in publish_commands
