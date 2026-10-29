"""Lossless, shared storage for complete query evaluations, with legacy reads."""

import argparse
import gzip
import hashlib
import io
import json
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

FORMAT = "ana-query-records-v1"
PACK_BYTES = 16 * 1024 * 1024
MAX_PACK_BYTES = 64 * 1024 * 1024
CACHE_BYTES = 80 * 1024 * 1024
_HASH = re.compile(r"[0-9a-f]{64}")


def canonical(value):
    """Match append_jsonl exactly; original member checksums remain authoritative."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def member_name(name):
    if not isinstance(name, str) or Path(name).name != name or not name.endswith(".jsonl"):
        raise ValueError("Invalid evaluation member name")
    return name


def hash_name(value):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError("Invalid evaluation object hash")
    return value


def atomic_write(path, payload):
    """Publish a complete artifact, never a partially written index or gzip file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class EvaluationReader:
    """Read original JSONL bytes, reconstructing compact members when necessary."""

    def __init__(self, folder, *, index_override=None):
        self.folder = Path(folder)
        self._packs = {}
        self._cache_bytes = 0
        self.pool = self.folder.parent / "_objects"
        if not self.pool.resolve().is_relative_to(self.folder.parent.resolve()):
            raise ValueError("Evaluation object pool escapes the archive")
        index = self.folder / "storage.json"
        if index.is_symlink():
            raise ValueError("Evaluation indices must not be symlinks")
        self.index = (
            index_override
            if index_override is not None
            else (json.loads(index.read_text()) if index.exists() else None)
        )
        if self.index is not None and self.index.get("format") != FORMAT:
            raise ValueError("Unsupported evaluation storage format")

    def pack(self, pack_hash):
        """Verify packed bytes, expansion bound and every record's content address."""
        if pack_hash in self._packs:
            records, size = self._packs.pop(pack_hash)
            self._packs[pack_hash] = (records, size)
            return records
        path = self.pool / (hash_name(pack_hash) + ".jsonl.gz")
        if path.is_symlink():
            raise ValueError("Evaluation objects must not be symlinks")
        if path.stat().st_size > MAX_PACK_BYTES + 1024 * 1024:
            raise ValueError("Evaluation pack exceeds its compressed size limit")
        compressed = path.read_bytes()
        if digest(compressed) != pack_hash:
            raise ValueError("Evaluation pack checksum mismatch")
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            payload = stream.read(MAX_PACK_BYTES + 1)
        if len(payload) > MAX_PACK_BYTES:
            raise ValueError("Evaluation pack exceeds its expansion limit")
        records = {}
        for line in payload.splitlines():
            item = json.loads(line)
            key, record = hash_name(item["sha256"]), item["record"]
            if not isinstance(record, dict) or "elapsed_s" in record:
                raise ValueError("Invalid packed evaluation record")
            if digest(canonical(record)) != key or key in records:
                raise ValueError("Evaluation record checksum mismatch or duplicate")
            records[key] = record
        # Bound cached source bytes, not pack count; Python object overhead is additional.
        if len(payload) <= CACHE_BYTES:
            while self._packs and self._cache_bytes + len(payload) > CACHE_BYTES:
                _, size = self._packs.pop(next(iter(self._packs)))
                self._cache_bytes -= size
            self._packs[pack_hash] = (records, len(payload))
            self._cache_bytes += len(payload)
        return records

    def read(self, filename, expected_sha256=None):
        """Return byte-identical original evidence, including order and elapsed times."""
        filename = member_name(filename)
        if self.index is None:
            path = self.folder / filename
            if path.is_symlink():
                raise ValueError("Evaluation members must not be symlinks")
            payload = path.read_bytes()
        else:
            entry = self.index["files"][filename]
            # Load each needed pack once per member, even if it exceeds the cache budget.
            needed = {}
            for ref in entry["records"]:
                needed.setdefault(hash_name(ref["pack"]), set()).add(hash_name(ref["object"]))
            objects = {}
            for pack_hash, keys in needed.items():
                records = self.pack(pack_hash)
                for key in keys:
                    objects[(pack_hash, key)] = records[key]
            lines = []
            for ref in entry["records"]:
                record = dict(objects[(ref["pack"], ref["object"])])
                if "elapsed_s" in ref:
                    record["elapsed_s"] = ref["elapsed_s"]
                lines.append(canonical(record) + b"\n")
            payload = b"".join(lines)
            if len(payload) != entry["bytes"] or digest(payload) != entry["sha256"]:
                raise ValueError("Reconstructed evaluation checksum mismatch")
        if expected_sha256 is not None and digest(payload) != expected_sha256:
            raise ValueError("Query evaluation checksum mismatch")
        return payload


def members(report):
    """Preserve the original manifest and its logical file names/checksums."""
    result = {"gold.jsonl": report["gold"]["sha256"]}
    for entry in report["baselines"].values():
        name = member_name(entry["file"])
        if name in result:
            raise ValueError("Duplicate evaluation member")
        result[name] = entry["sha256"]
    return result


def compact_evaluations(root, folders=None):
    """Deduplicate complete evaluations; remove raw members only after exact verification.

    elapsed_s stays in each evaluation's index. Every other field is immutable
    record content. A crash before cleanup can leave both formats, not lost data.
    """
    root = Path(root).resolve()
    folders = list(folders) if folders is not None else sorted(root.glob("*/manifest.json"))
    folders = [Path(p).parent if Path(p).name == "manifest.json" else Path(p) for p in folders]
    if not folders:
        raise ValueError("No evaluations found")
    for folder in folders:
        if folder.resolve().parent != root:
            raise ValueError("Evaluation folder must be a direct child of the storage root")
    pool = root / "_objects"
    reader = EvaluationReader(folders[0])
    locations, pending, plans = {}, {}, []
    for path in sorted(pool.glob("*.jsonl.gz")):
        pack_hash = path.name.removesuffix(".jsonl.gz")
        for key in reader.pack(pack_hash):
            locations.setdefault(key, pack_hash)
    original_bytes = 0
    manifests = {}
    for folder in folders:
        manifests[folder] = (folder / "manifest.json").read_bytes()
        report = json.loads(manifests[folder])
        if report["status"] != "complete" or report["snapshot_before"] != report["snapshot_after"]:
            raise ValueError("Only complete, unchanged-graph evaluations can be compacted")
        source = EvaluationReader(folder)
        files = {}
        for filename, sha in members(report).items():
            payload = source.read(filename, sha)
            if b"\n".join(payload.splitlines()) + b"\n" != payload:
                raise ValueError("Noncanonical line endings cannot be compacted losslessly")
            original_bytes += len(payload)
            refs = []
            for line in payload.splitlines():
                record = json.loads(line)
                if not isinstance(record, dict) or canonical(record) != line:
                    raise ValueError("Noncanonical evaluation cannot be compacted losslessly")
                ref = {}
                if "elapsed_s" in record:
                    ref["elapsed_s"] = record.pop("elapsed_s")
                core = canonical(record)
                key = digest(core)
                ref["object"] = key
                if key not in locations:
                    pending.setdefault(key, core)
                refs.append(ref)
            if not refs:
                raise ValueError("Empty evaluation member")
            files[filename] = {"sha256": sha, "bytes": len(payload), "records": refs}
        plans.append((folder, files))

    def publish_pack(lines):
        payload = b"".join(lines)
        buffer = io.BytesIO()
        with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as stream:
            stream.write(payload)
        compressed = buffer.getvalue()
        pack_hash = digest(compressed)
        path = pool / (pack_hash + ".jsonl.gz")
        if path.exists() and path.read_bytes() != compressed:
            raise ValueError("Existing evaluation object is corrupt")
        if not path.exists():
            atomic_write(path, compressed)
        for line in lines:
            locations[json.loads(line)["sha256"]] = pack_hash

    lines, size = [], 0
    for key, core in sorted(pending.items()):
        line = b'{"record": ' + core + b', "sha256": "' + key.encode() + b'"}\n'
        if len(line) > MAX_PACK_BYTES:
            raise ValueError("Evaluation record exceeds the pack limit")
        if lines and size + len(line) > PACK_BYTES:
            publish_pack(lines)
            lines, size = [], 0
        lines.append(line)
        size += len(line)
    if lines:
        publish_pack(lines)
    indices = []
    for folder, files in plans:
        for entry in files.values():
            for ref in entry["records"]:
                ref["pack"] = locations[ref["object"]]
        index = {"format": FORMAT, "files": files}
        source = EvaluationReader(folder, index_override=index)
        for name, entry in files.items():
            payload = source.read(name, entry["sha256"])
            original = folder / name
            if original.exists() and original.read_bytes() != payload:
                raise ValueError("Original evaluation changed during compaction")
        indices.append((folder, index))
    # Publish only after reconstructing every member byte-for-byte successfully.
    for folder, original in manifests.items():
        if (folder / "manifest.json").read_bytes() != original:
            raise ValueError("Evaluation manifest changed during compaction")
    for folder, index in indices:
        atomic_write(folder / "storage.json", canonical(index) + b"\n")
    for folder, files in plans:
        for name in files:
            original = folder / name
            if original.exists() and digest(original.read_bytes()) != files[name]["sha256"]:
                raise ValueError("Original evaluation changed before cleanup")
            original.unlink(missing_ok=True)
    return {
        "evaluations": len(plans),
        "logical_bytes": original_bytes,
        "objects": len(locations),
        "packs": len(list(pool.glob("*.jsonl.gz"))),
    }


def export_evaluation(folder, output):
    """Materialize the original standalone files, without touching the compact archive."""
    folder, output = Path(folder), Path(output)
    if output.exists():
        raise ValueError("Export output must not exist")
    report_bytes = (folder / "manifest.json").read_bytes()
    report = json.loads(report_bytes)
    reader = EvaluationReader(folder)
    payloads = {name: reader.read(name, sha) for name, sha in members(report).items()}
    output.mkdir(parents=True)
    (output / "manifest.json").write_bytes(report_bytes)
    for name, payload in payloads.items():
        (output / name).write_bytes(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compact = commands.add_parser("compact")
    compact.add_argument("--root", type=Path, required=True)
    export = commands.add_parser("export")
    export.add_argument("evaluation", type=Path)
    export.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "compact":
        print(json.dumps(compact_evaluations(args.root), sort_keys=True))
    else:
        export_evaluation(args.evaluation, args.out)
        print(f"Exported original evidence to {args.out}")


if __name__ == "__main__":
    main()
