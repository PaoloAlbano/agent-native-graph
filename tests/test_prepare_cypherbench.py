import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent_native_graph.research.prepare_cypherbench import _load_from_source_dir


def test_local_json_source_does_not_require_pandas(tmp_path: Path) -> None:
    (tmp_path / "test.json").write_text(
        json.dumps([{"qid": "one", "graph": "company"}]), encoding="utf-8"
    )
    assert _load_from_source_dir(tmp_path, "test") == [{"qid": "one", "graph": "company"}]
