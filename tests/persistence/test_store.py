"""RedisStore tests with a fake client (no Redis server needed)."""

from __future__ import annotations

import json
import sys

import pytest

from compiler.graph import build_graph
from compiler.knowledge import Entity, KnowledgeBase
from compiler.persistence import PersistenceError, RedisStore


class FakeRedis:
    """The tiny part of the redis client the store uses."""

    def __init__(self, *, ping: bool = True) -> None:
        self.data = {}
        self.closed = False
        self._ping = ping

    def set(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def ping(self):
        if self._ping is False:
            raise ConnectionError("redis is down")
        return True

    def close(self):
        self.closed = True


def sample_kb() -> KnowledgeBase:
    return KnowledgeBase(
        entities=[Entity(name="解析器", type="system", description="组件")],
        documents=[{"id": "docA", "title": "解析器", "source": "a.md"}],
    )


def test_knowledge_base_round_trip() -> None:
    client = FakeRedis()
    store = RedisStore(client)

    key = store.save_knowledge_base(sample_kb(), "demo")
    loaded = store.load_knowledge_base("demo")

    assert key == "lwc:kb:demo"
    assert loaded.entities[0].name == "解析器"
    assert loaded.documents[0]["id"] == "docA"
    assert isinstance(client.data["lwc:kb:demo"], str)


def test_graph_round_trip() -> None:
    client = FakeRedis()
    store = RedisStore(client)
    graph = build_graph(sample_kb())

    store.save_graph(graph, "demo")
    loaded = store.load_graph("demo")

    assert loaded.to_dict() == graph.to_dict()
    assert store.graph_key("demo") == "lwc:graph:demo"


def test_namespace_is_configurable() -> None:
    store = RedisStore(FakeRedis(), namespace="wiki")

    assert store.kb_key("x") == "wiki:kb:x"
    assert store.graph_key("x") == "wiki:graph:x"


def test_missing_key_is_reported() -> None:
    store = RedisStore(FakeRedis())

    with pytest.raises(PersistenceError) as error:
        store.load_knowledge_base("nope")

    assert "no state stored" in str(error.value)


def test_bytes_payload_is_decoded() -> None:
    client = FakeRedis()
    client.data["lwc:graph:demo"] = json.dumps(
        {"nodes": [], "edges": [], "metadata": {}}
    ).encode("utf-8")

    graph = RedisStore(client).load_graph("demo")

    assert graph.to_dict()["nodes"] == []


def test_broken_payload_is_reported() -> None:
    client = FakeRedis()
    client.data["lwc:kb:demo"] = "{not json"

    with pytest.raises(PersistenceError) as error:
        RedisStore(client).load_knowledge_base("demo")

    assert "not valid JSON" in str(error.value)


def test_non_object_payload_is_reported() -> None:
    client = FakeRedis()
    client.data["lwc:kb:demo"] = "[1, 2, 3]"

    with pytest.raises(PersistenceError) as error:
        RedisStore(client).load_knowledge_base("demo")

    assert "must be a JSON object" in str(error.value)


def test_ping_reports_unavailable_redis() -> None:
    assert RedisStore(FakeRedis()).ping() is True
    assert RedisStore(FakeRedis(ping=False)).ping() is False


def test_close_is_forwarded() -> None:
    client = FakeRedis()
    store = RedisStore(client)

    store.close()

    assert client.closed is True


def test_missing_redis_package_gives_a_clear_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "redis", None)

    with pytest.raises(PersistenceError) as error:
        RedisStore().client

    assert "pip install redis" in str(error.value)
