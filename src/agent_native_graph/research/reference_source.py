"""Bind reference imports to an auditable source tree without modifying its checkout."""

import hashlib
import importlib
import json
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


@contextmanager
def reference_source(repo: Path, commit: str | None = None):
    """Export pinned Python/config blobs and scope imports to that exact source.

    Datasets remain in the original checkout. Cached reference modules are rejected
    rather than silently reusing code from another revision.
    """
    if any(name == "multigraphrag" or name.startswith("multigraphrag.") for name in sys.modules):
        raise ValueError("Reference modules are already imported; start a fresh process")
    if commit is not None and not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ValueError("--reference-commit must be a full 40-character Git commit")
    revision = (
        _git(repo, "rev-parse", "--verify", f"{commit or 'HEAD'}^{{commit}}").decode().strip()
    )
    with TemporaryDirectory(prefix="ana-reference-") as temporary:
        root = Path(temporary) if commit else repo
        if commit:
            entries = _git(
                repo, "ls-tree", "-r", "-z", revision, "src", "pyproject.toml", "uv.lock"
            )
            for entry in entries.split(b"\0"):
                if not entry:
                    continue
                header, raw_path = entry.split(b"\t", 1)
                mode, kind, oid = header.decode().split()
                path = PurePosixPath(raw_path.decode())
                if (
                    kind != "blob"
                    or mode not in ("100644", "100755")
                    or path.is_absolute()
                    or ".." in path.parts
                ):
                    raise ValueError("Unsafe reference source entry")
                target = root.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(_git(repo, "cat-file", "blob", oid))
        if not (root / "src/multigraphrag/__init__.py").is_file():
            raise ValueError("Reference source package is missing")
        files = sorted(
            p for p in (root / "src").rglob("*") if p.is_file() and "__pycache__" not in p.parts
        )
        files += [p for p in (root / "pyproject.toml", root / "uv.lock") if p.is_file()]
        hashes = {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
        }
        metadata = {
            "source_mode": "pinned-git-export" if commit else "working-checkout",
            "source_commit": revision,
            "source_files": hashes,
            "source_sha256": hashlib.sha256(
                json.dumps(hashes, sort_keys=True).encode()
            ).hexdigest(),
        }
        original_path = sys.path[:]
        sys.path.insert(0, str(root / "src"))
        try:
            package = importlib.import_module("multigraphrag")
            if (
                Path(package.__file__).resolve()
                != (root / "src/multigraphrag/__init__.py").resolve()
            ):
                raise ValueError("Reference package did not resolve to the selected source")
            yield metadata
        finally:
            sys.path[:] = original_path
            for name in list(sys.modules):
                if name == "multigraphrag" or name.startswith("multigraphrag."):
                    del sys.modules[name]
