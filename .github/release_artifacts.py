"""Validate release identity and distribution contents before granting publish access."""

import argparse
import hashlib
import re
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path


def validate_version(root: Path, tag: str) -> str:
    """Require a stable tag matching both the project and locked local package."""
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    version = project["version"]
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or tag != f"v{version}":
        raise ValueError(f"Expected stable release tag v{version}, got {tag!r}")
    lock = tomllib.loads((root / "uv.lock").read_text())
    local = [p for p in lock["package"] if p["name"] == project["name"]]
    if len(local) != 1 or local[0]["version"] != version:
        raise ValueError("uv.lock project version does not match pyproject.toml")
    return version


def validate_artifacts(root: Path, dist: Path, version: str) -> None:
    """Audit wheel/sdist allowlists and metadata, then checksum the deliverables."""
    wheel = dist / f"agent_native_graph-{version}-py3-none-any.whl"
    source = dist / f"agent_native_graph-{version}.tar.gz"
    # uv creates this marker in output directories; it is not a release asset.
    marker = dist / ".gitignore"
    if marker.exists() and marker.read_text().strip() != "*":
        raise ValueError("Unexpected dist/.gitignore contents")
    expected = {wheel.name, source.name, "SHA256SUMS", ".gitignore"}
    if {p.name for p in dist.iterdir()} - expected or not wheel.is_file() or not source.is_file():
        raise ValueError("dist must contain exactly one project wheel and sdist (plus SHA256SUMS)")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        prefix = f"agent_native_graph-{version}.dist-info/"
        for name in names:
            parts = Path(name).parts
            if (
                name.startswith("/")
                or ".." in parts
                or any(p.startswith(".") or p == "__pycache__" for p in parts)
                or not name.startswith(("agent_native_graph/", prefix))
                or name.endswith((".pyc", ".pyo"))
            ):
                raise ValueError(f"Unexpected wheel member: {name}")
        metadata = Parser().parsestr(archive.read(prefix + "METADATA").decode())
        if metadata["Name"] != "agent-native-graph" or metadata["Version"] != version:
            raise ValueError("Wheel metadata does not match release identity")
        required = ["agent_native_graph/__init__.py", "agent_native_graph/interfaces/cli.py"]
        required += [
            str(p.relative_to(root / "src"))
            for p in (root / "src/agent_native_graph").rglob("*.yaml")
        ]
        if not set(required) <= set(names):
            raise ValueError("Wheel is missing package code or bundled YAML profiles")
    with tarfile.open(source) as archive:
        names = set()
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] != f"agent_native_graph-{version}" or ".." in parts:
                raise ValueError(f"Unexpected sdist member: {member.name}")
            if member.isdir():
                continue
            relative = "/".join(parts[1:])
            if (
                not member.isfile()
                or not (
                    relative.startswith("src/agent_native_graph/")
                    or relative
                    in {
                        "pyproject.toml",
                        "uv.lock",
                        "README.md",
                        "LICENSE",
                        "PKG-INFO",
                        ".gitignore",
                    }
                )
                or (
                    relative != ".gitignore"
                    and any(p.startswith(".") or p == "__pycache__" for p in parts)
                )
                or relative.endswith((".pyc", ".pyo"))
            ):
                raise ValueError(f"Unexpected sdist member: {member.name}")
            names.add(relative)
        if (
            not {
                "pyproject.toml",
                "uv.lock",
                "README.md",
                "LICENSE",
                "src/agent_native_graph/__init__.py",
            }
            <= names
        ):
            raise ValueError("Source distribution is missing required project files")
    checksums = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in (wheel, source)
    ]
    (dist / "SHA256SUMS").write_text("".join(checksums))


def main() -> None:
    """Run from CI or make check-release without invoking network or publishing tools."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dist", type=Path)
    args = parser.parse_args()
    version = validate_version(args.root, args.tag)
    if args.dist:
        validate_artifacts(args.root, args.dist, version)
    print(f"Release identity verified: {args.tag}")


if __name__ == "__main__":
    main()
