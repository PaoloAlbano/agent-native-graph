"""Protect the code-check/build/deploy boundary without requiring GitHub credentials."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    # BaseLoader keeps GitHub's "on" key instead of YAML 1.1's boolean coercion.
    return yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)


def commands(job):
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_ci_runs_lint_before_tests_on_branches_and_main():
    ci = workflow("ci.yml")
    assert set(ci["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert ci["on"]["push"]["branches"] == ["**"]
    assert ci["permissions"] == {"contents": "read"}
    assert set(ci["jobs"]) == {"lint", "tests", "documentation", "deploy"}
    lint, tests = ci["jobs"]["lint"], ci["jobs"]["tests"]
    assert lint["name"] == "Lint and Format"
    assert tests["name"] == "Code Tests" and tests["needs"] == "lint"
    assert "make lint" in commands(lint)
    assert "ruff format --check src/agent_native_graph tests examples" in commands(lint)
    assert "make test" in commands(tests)
    assert "pytest" not in commands(lint) and "make test" not in commands(lint)
    assert "node --check" in commands(lint)
    assert "node --test tests/docs_results_ui.test.cjs" in commands(tests)


def test_code_jobs_need_no_external_checkout_or_secrets():
    jobs = workflow("ci.yml")["jobs"]
    for job in (jobs["lint"], jobs["tests"]):
        assert "uv sync --locked --extra dev --extra service" in commands(job)
        assert "secrets." not in str(job)
        assert "ANA_TEST_NEO4J=1" not in commands(job)
        assert "ANA_TEST_REFERENCE=1" not in commands(job)
        assert all(not step.get("with", {}).get("repository") for step in job["steps"])


def test_documentation_build_depends_on_code_checks_without_repeating_tests():
    job = workflow("ci.yml")["jobs"]["documentation"]
    assert job["uses"] == "./.github/workflows/docs.yml" and job["needs"] == "tests"
    docs = workflow("docs.yml")
    assert set(docs["on"]) == {"workflow_call"}
    publish = docs["on"]["workflow_call"]["inputs"]["publish"]
    assert publish["type"] == "boolean" and publish["default"] == "false"
    assert docs["permissions"] == {"contents": "read"}
    assert set(docs["jobs"]) == {"build"}
    build = docs["jobs"]["build"]
    assert "Check Documentation Build" in build["name"]
    assert "Build Release Documentation" in build["name"]
    assert "make docs-build DOCS_OUT=build/site REFERENCE_REPO=build/reference" in commands(build)
    assert "pytest" not in commands(build) and "make test" not in commands(build)
    assert "ruff" not in commands(build) and "node --test" not in commands(build)
    assert any(step.get("with", {}).get("path") == "build/reference" for step in build["steps"])


def test_pages_publication_is_gated_on_main_and_successful_build():
    ci, docs = workflow("ci.yml"), workflow("docs.yml")
    deploy = ci["jobs"]["deploy"]
    assert deploy["name"] == "Publish GitHub Pages" and deploy["needs"] == "documentation"
    assert deploy["if"] == "github.event_name != 'pull_request' && github.ref == 'refs/heads/main'"
    assert ci["jobs"]["documentation"]["with"]["publish"] == "${{ " + deploy["if"] + " }}"
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    artifact = next(
        step
        for step in docs["jobs"]["build"]["steps"]
        if step.get("uses", "").startswith("actions/upload-pages-artifact@")
    )
    assert artifact["if"] == "inputs.publish && " + deploy["if"]
    assert artifact["with"]["path"] == "build/site"
    assert artifact["with"]["include-hidden-files"] == "true"


def test_changes_to_either_workflow_trigger_checks():
    triggers = workflow("ci.yml")["on"]
    for event in ("push", "pull_request"):
        assert "paths" not in (triggers[event] or {})
        assert "paths-ignore" not in (triggers[event] or {})
    assert workflow("ci.yml")["concurrency"]["group"] == "ci-${{ github.ref }}"


def test_runners_and_external_actions_are_pinned_consistently():
    """Avoid silent OS migrations and mutable Action tags across all workflows."""
    refs = {}
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        config = workflow(path.name)
        for job in config["jobs"].values():
            if "uses" in job:
                assert job["uses"].startswith("./.github/workflows/")
                continue
            assert job["runs-on"] == "ubuntu-24.04", path.name
            for step in job.get("steps", []):
                if "uses" not in step:
                    continue
                action, ref = step["uses"].rsplit("@", 1)
                assert re.fullmatch(r"[a-f0-9]{40}", ref), step["uses"]
                assert refs.setdefault(action, ref) == ref, action
        source = path.read_text()
        assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24" not in source
        assert "ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION" not in source


def test_release_artifact_upgrades_preserve_names_and_strict_digest_checks():
    """Keep the archived producer/consumer protocol when upgrading artifact Actions."""
    release = workflow("release.yml")
    uploads = [
        s
        for s in release["jobs"]["build"]["steps"]
        if s.get("uses", "").startswith("actions/upload-artifact@")
    ]
    downloads = [
        s
        for s in release["jobs"]["publish"]["steps"]
        if s.get("uses", "").startswith("actions/download-artifact@")
    ]
    assert {s["with"]["name"] for s in uploads} == {"python-distributions", "tested-image"}
    assert {s["with"]["name"] for s in downloads} == {s["with"]["name"] for s in uploads}
    assert all(s["with"]["archive"] == "true" for s in uploads)
    assert all(s["with"]["digest-mismatch"] == "error" for s in downloads)
