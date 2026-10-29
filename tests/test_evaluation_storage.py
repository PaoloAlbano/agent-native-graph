"""Storage changes must never rewrite historical evaluation evidence."""

import gzip
import json

import pytest

from agent_native_graph.research import evaluation_storage as storage


def evaluation(root, name="first", elapsed=0.25):
    folder = root / name
    folder.mkdir()
    rows = [
        {"qid": "a", "rows": [["città"]], "ok": True, "elapsed_s": elapsed},
        {"qid": "b", "rows": [], "ok": False, "error": "timeout"},
    ]
    payload = b"".join(storage.canonical(row) + b"\n" for row in rows)
    for filename in ("gold.jsonl", "baseline.jsonl"):
        (folder / filename).write_bytes(payload)
    report = {
        "status": "complete",
        "snapshot_before": {"graph": "unchanged"},
        "snapshot_after": {"graph": "unchanged"},
        "gold": {"sha256": storage.digest(payload)},
        "baselines": {"direct": {"file": "baseline.jsonl", "sha256": storage.digest(payload)}},
    }
    (folder / "manifest.json").write_bytes(storage.canonical(report) + b"\n")
    return folder, payload


def test_legacy_reads_remain_supported(tmp_path):
    folder, payload = evaluation(tmp_path)
    assert storage.EvaluationReader(folder).read("gold.jsonl", storage.digest(payload)) == payload


def test_lossless_deduplication_export_and_idempotence(tmp_path):
    first, one = evaluation(tmp_path)
    second, two = evaluation(tmp_path, "second", elapsed=0.123456789)
    manifests = {p: (p / "manifest.json").read_bytes() for p in (first, second)}
    result = storage.compact_evaluations(tmp_path)
    assert result == {
        "evaluations": 2,
        "logical_bytes": 2 * (len(one) + len(two)),
        "objects": 2,
        "packs": 1,
    }
    for folder, payload in ((first, one), (second, two)):
        assert (folder / "manifest.json").read_bytes() == manifests[folder]
        assert not list(folder.glob("*.jsonl"))
        reader = storage.EvaluationReader(folder)
        assert reader.read("gold.jsonl") == reader.read("baseline.jsonl") == payload
    index = (first / "storage.json").read_bytes()
    assert storage.compact_evaluations(tmp_path) == result
    assert (first / "storage.json").read_bytes() == index
    exported = tmp_path / "exported"
    storage.export_evaluation(second, exported)
    assert (exported / "manifest.json").read_bytes() == manifests[second]
    assert storage.EvaluationReader(exported).read("gold.jsonl") == two
    with pytest.raises(ValueError, match="must not exist"):
        storage.export_evaluation(second, exported)


def test_new_evaluation_reuses_existing_objects(tmp_path):
    evaluation(tmp_path)
    storage.compact_evaluations(tmp_path)
    packs = list((tmp_path / "_objects").glob("*"))
    second, payload = evaluation(tmp_path, "second", elapsed=9)
    result = storage.compact_evaluations(tmp_path, folders=[second])
    assert result["objects"] == 2 and result["packs"] == 1
    assert list((tmp_path / "_objects").glob("*")) == packs
    assert storage.EvaluationReader(second).read("gold.jsonl") == payload


@pytest.mark.parametrize("change", ["failed", "graph", "newline", "canonical", "checksum"])
def test_invalid_input_is_never_deleted(tmp_path, change):
    folder, payload = evaluation(tmp_path)
    manifest = folder / "manifest.json"
    report = json.loads(manifest.read_bytes())
    if change == "failed":
        report["status"] = "failed"
    elif change == "graph":
        report["snapshot_after"] = {"graph": "changed"}
    else:
        if change == "newline":
            payload = payload.replace(b"\n", b"\r\n")
        elif change == "canonical":
            payload = payload.replace(b'"ok": true', b'"ok":true')
        else:
            payload += b"{}\n"
        (folder / "gold.jsonl").write_bytes(payload)
        if change != "checksum":
            report["gold"]["sha256"] = storage.digest(payload)
    manifest.write_bytes(storage.canonical(report))
    with pytest.raises(ValueError):
        storage.compact_evaluations(tmp_path)
    assert (folder / "gold.jsonl").read_bytes() == payload
    assert (folder / "baseline.jsonl").exists()
    assert not (folder / "storage.json").exists()


@pytest.mark.parametrize("change", ["elapsed", "order", "pack", "object", "version"])
def test_corrupt_index_is_not_silently_accepted(tmp_path, change):
    folder, _ = evaluation(tmp_path)
    storage.compact_evaluations(tmp_path)
    path = folder / "storage.json"
    index = json.loads(path.read_bytes())
    refs = index["files"]["gold.jsonl"]["records"]
    if change == "elapsed":
        refs[0]["elapsed_s"] = 99
    elif change == "order":
        refs.reverse()
    elif change == "version":
        index["format"] = "unknown"
    else:
        refs[0][change] = "../escape"
    path.write_bytes(storage.canonical(index))
    with pytest.raises(ValueError):
        storage.EvaluationReader(folder).read("gold.jsonl")


def test_corrupt_pack_is_rejected(tmp_path):
    folder, _ = evaluation(tmp_path)
    storage.compact_evaluations(tmp_path)
    pack = next((tmp_path / "_objects").glob("*"))
    pack.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        storage.EvaluationReader(folder).read("gold.jsonl")


def test_record_hash_is_independently_checked(tmp_path):
    folder, _ = evaluation(tmp_path)
    pool = tmp_path / "_objects"
    pool.mkdir()
    payload = storage.canonical({"sha256": "0" * 64, "record": {"qid": "tampered"}}) + b"\n"
    compressed = gzip.compress(payload, mtime=0)
    key = storage.digest(compressed)
    (pool / (key + ".jsonl.gz")).write_bytes(compressed)
    with pytest.raises(ValueError, match="record checksum"):
        storage.EvaluationReader(folder).pack(key)


def test_bounded_pack_expansion(tmp_path, monkeypatch):
    folder, _ = evaluation(tmp_path)
    pool = tmp_path / "_objects"
    pool.mkdir()
    compressed = gzip.compress(b"x" * 10000, mtime=0)
    key = storage.digest(compressed)
    (pool / (key + ".jsonl.gz")).write_bytes(compressed)
    monkeypatch.setattr(storage, "MAX_PACK_BYTES", 100)
    with pytest.raises(ValueError, match="expansion limit"):
        storage.EvaluationReader(folder).pack(key)


@pytest.mark.parametrize("name", ["../gold.jsonl", "/gold.jsonl", "gold.txt"])
def test_member_paths_are_confined(tmp_path, name):
    folder, _ = evaluation(tmp_path)
    with pytest.raises(ValueError, match="member name"):
        storage.EvaluationReader(folder).read(name)


def test_verification_failure_preserves_originals(tmp_path, monkeypatch):
    folder, payload = evaluation(tmp_path)
    original = storage.EvaluationReader.read

    def fail_validation(self, *args, **kwargs):
        if self.index is not None:
            raise ValueError("injected verification failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(storage.EvaluationReader, "read", fail_validation)
    with pytest.raises(ValueError, match="injected"):
        storage.compact_evaluations(tmp_path)
    assert (folder / "gold.jsonl").read_bytes() == payload
    assert not (folder / "storage.json").exists()


def test_multiple_packs_and_missing_object(tmp_path, monkeypatch):
    folder, payload = evaluation(tmp_path)
    monkeypatch.setattr(storage, "PACK_BYTES", 1)
    assert storage.compact_evaluations(tmp_path)["packs"] == 2
    assert storage.EvaluationReader(folder).read("gold.jsonl") == payload
    next((tmp_path / "_objects").glob("*")).unlink()
    with pytest.raises(FileNotFoundError):
        storage.EvaluationReader(folder).read("gold.jsonl")


def test_cache_budget_does_not_change_evidence(tmp_path, monkeypatch):
    folder, payload = evaluation(tmp_path)
    monkeypatch.setattr(storage, "PACK_BYTES", 1)
    storage.compact_evaluations(tmp_path)
    monkeypatch.setattr(storage, "CACHE_BYTES", 200)
    reader = storage.EvaluationReader(folder)
    assert reader.read("gold.jsonl") == payload
    assert reader._cache_bytes <= 200
    monkeypatch.setattr(storage, "CACHE_BYTES", 0)
    fresh = storage.EvaluationReader(folder)
    assert fresh.read("gold.jsonl") == payload
    assert not fresh._packs


@pytest.mark.parametrize("target", ["gold.jsonl", "storage.json", "_objects"])
def test_symlinks_cannot_redirect_evidence_reads(tmp_path, target):
    folder, _ = evaluation(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    if target == "_objects":
        (tmp_path / target).symlink_to(external, target_is_directory=True)
        # A pool outside the archive is rejected before any reads.
        outside = tmp_path.parent / (tmp_path.name + "-outside")
        (tmp_path / target).unlink()
        (tmp_path / target).symlink_to(outside, target_is_directory=True)
    else:
        path = folder / target
        path.unlink(missing_ok=True)
        path.symlink_to(external / "redirected")
    with pytest.raises(ValueError):
        storage.EvaluationReader(folder).read("gold.jsonl")


def test_changed_manifest_aborts_before_cleanup(tmp_path, monkeypatch):
    folder, payload = evaluation(tmp_path)
    original = storage.EvaluationReader.read

    def change_manifest(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if self.index is not None:
            (folder / "manifest.json").write_bytes(b"{}")
        return result

    monkeypatch.setattr(storage.EvaluationReader, "read", change_manifest)
    with pytest.raises(ValueError, match="manifest changed"):
        storage.compact_evaluations(tmp_path)
    assert (folder / "gold.jsonl").read_bytes() == payload
    assert not (folder / "storage.json").exists()
