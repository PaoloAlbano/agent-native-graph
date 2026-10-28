from unittest.mock import MagicMock

import pytest

from agent_native_graph import connect_neo4j
from agent_native_graph.backends.neo4j import backend, introspection
from agent_native_graph.backends.neo4j.config import Neo4jConfig


def test_named_database_is_used_by_discovery_and_data_queries(monkeypatch):
    metadata_driver, data_driver = MagicMock(), MagicMock()
    data_driver.session.return_value.__enter__.return_value.run.return_value.single.return_value = {
        "count": 2
    }
    monkeypatch.setattr(
        backend.GraphDatabase, "driver", MagicMock(side_effect=[metadata_driver, data_driver])
    )
    with connect_neo4j(
        "bolt://example.invalid", "reader", "secret", database="domain-graph"
    ) as graph:
        result = graph.call("count_nodes", {"label": "Device", "alias": "count"})
        assert graph.call("fetch", {"from": result["handle"]})["rows"] == [[2]]
    metadata_driver.session.assert_called_once_with(database="domain-graph")
    data_driver.session.assert_called_once_with(database="domain-graph")
    metadata_driver.close.assert_called_once()
    data_driver.close.assert_called_once()


def test_default_database_preserves_the_driver_default(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(backend.GraphDatabase, "driver", MagicMock(return_value=driver))
    with connect_neo4j("bolt://example.invalid", "reader", "secret", schema={}) as graph:
        graph.call("count_nodes", {"label": "Device"})
    driver.session.assert_called_once_with()


def test_discovery_failure_closes_metadata_driver_in_named_database(monkeypatch):
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value.run.side_effect = RuntimeError(
        "discovery failed"
    )
    connect = MagicMock(return_value=driver)
    monkeypatch.setattr(backend.GraphDatabase, "driver", connect)
    with pytest.raises(RuntimeError, match="discovery failed"):
        connect_neo4j("bolt://example.invalid", "reader", "secret", database="domain-graph")
    driver.session.assert_called_once_with(database="domain-graph")
    driver.close.assert_called_once()
    connect.assert_called_once()


@pytest.mark.parametrize("database", ["", " ", 123, False])
def test_bad_database_is_rejected_before_discovery(monkeypatch, database):
    discover = MagicMock()
    monkeypatch.setattr(introspection, "introspect_schema", discover)
    with pytest.raises(ValueError, match="database"):
        connect_neo4j("bolt://example.invalid", "reader", "secret", database=database)
    discover.assert_not_called()


def test_environment_config_is_an_immutable_snapshot_without_credentials_in_repr(monkeypatch):
    monkeypatch.setenv("NEO4J_DATABASE", "domain-graph")
    monkeypatch.setenv("NEO4J_URI", "bolt://private-host:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "not-public")
    config = Neo4jConfig.from_env()
    monkeypatch.setenv("NEO4J_DATABASE", "changed")
    assert config.database == "domain-graph"
    assert "not-public" not in repr(config) and "private-host" not in repr(config)


def test_public_factory_handles_are_not_confused_between_workflows(monkeypatch):
    monkeypatch.setattr(
        backend.GraphDatabase, "driver", MagicMock(side_effect=[MagicMock(), MagicMock()])
    )
    with (
        connect_neo4j("bolt://example.invalid", "reader", "secret", schema={}) as a,
        connect_neo4j("bolt://example.invalid", "reader", "secret", schema={}) as b,
    ):
        ha = a._store([{"value": "A"}], kind="table", columns=["value"])["handle"]
        hb = b._store([{"value": "B"}], kind="table", columns=["value"])["handle"]
        assert ha != hb
        with pytest.raises(ValueError, match="Unknown handle"):
            b.call("fetch", {"from": ha})
