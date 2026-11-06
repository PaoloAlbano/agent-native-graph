"""Compact handle names are scoped by workflows, independently of entity identity."""

import pytest

from agent_native_graph.core.handle_store import HandleStore


def test_isolated_stores_share_short_names_but_not_state_or_namespace():
    first, second = HandleStore.isolated(), HandleStore.isolated()
    a = first.store([{"value": "A"}])
    b = second.store([{"value": "B"}])
    assert a["handle"] == b["handle"] == "h1"
    assert first.namespace != second.namespace
    assert first.get("h1").rows == [{"value": "A"}]
    assert second.get("h1").rows == [{"value": "B"}]


def test_namespaced_format_is_still_available():
    store = HandleStore(namespace="workflow", compact_ids=False)
    assert store.store([])["handle"] == "hworkflow-1"
    assert HandleStore().store([])["handle"] == "h1"


def test_format_must_be_selected_before_the_first_handle():
    store = HandleStore(namespace="workflow")
    store.use_compact_ids()
    assert store.store([])["handle"] == "h1"
    with pytest.raises(ValueError, match="before creating handles"):
        store.use_compact_ids()


def test_clear_does_not_reuse_a_previous_name_in_the_same_store():
    store = HandleStore.isolated()
    store.store([])
    store.clear()
    assert store.store([])["handle"] == "h2"


def test_handle_summaries_and_repair_hint_follow_creation_order():
    store = HandleStore.isolated()
    for index in range(12):
        store.store([{"value": index}])
    assert [item["handle"] for item in store.available_summaries()] == [
        f"h{index}" for index in range(1, 13)
    ]
    with pytest.raises(ValueError, match="latest available handle is 'h12'"):
        store.get("missing")
