"""Store compiled artefacts in Redis (optional feature).

Redis is a runtime store here, not a replacement for the files the pipeline
writes: the KnowledgeBase and the Graph are saved as JSON values, so a later run
can pick them up without re-parsing sources or calling the LLM again.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ..graph import Graph
from ..knowledge import KnowledgeBase
from .health import PersistenceError

DEFAULT_NAMESPACE = "lwc"


class RedisStore:
    """Save and load ``KnowledgeBase`` / ``Graph`` objects in Redis.

    The ``redis`` client is imported lazily: the rest of the compiler works
    without it, and only this class needs the dependency.
    """

    def __init__(
        self,
        client: Any = None,
        *,
        host: str = "127.0.0.1",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        namespace: str = DEFAULT_NAMESPACE,
    ) -> None:
        self.namespace = namespace
        self._client = client
        self._options: Dict[str, Any] = {
            "host": host,
            "port": port,
            "db": db,
            "password": password,
        }

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._connect()
        return self._client

    def ping(self) -> bool:
        """``True`` when Redis answers; never raises."""

        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # pragma: no cover - best effort
                pass

    def save_knowledge_base(
        self, knowledge_base: KnowledgeBase, key: str = "default"
    ) -> str:
        return self._save(self.kb_key(key), knowledge_base.to_dict())

    def load_knowledge_base(self, key: str = "default") -> KnowledgeBase:
        return KnowledgeBase.from_dict(self._load(self.kb_key(key)))

    def save_graph(self, graph: Graph, key: str = "default") -> str:
        return self._save(self.graph_key(key), graph.to_dict())

    def load_graph(self, key: str = "default") -> Graph:
        return Graph.from_dict(self._load(self.graph_key(key)))

    def kb_key(self, key: str) -> str:
        return f"{self.namespace}:kb:{key}"

    def graph_key(self, key: str) -> str:
        return f"{self.namespace}:graph:{key}"

    def _save(self, redis_key: str, payload: Dict[str, Any]) -> str:
        self.client.set(redis_key, json.dumps(payload, ensure_ascii=False))
        return redis_key

    def _load(self, redis_key: str) -> Dict[str, Any]:
        raw = self.client.get(redis_key)
        if raw is None:
            raise PersistenceError(f"no state stored under '{redis_key}'")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise PersistenceError(
                f"state under '{redis_key}' is not valid JSON: {error}"
            ) from error
        if not isinstance(payload, dict):
            raise PersistenceError(
                f"state under '{redis_key}' must be a JSON object"
            )
        return payload

    def _connect(self) -> Any:
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError as exc:
            raise PersistenceError(
                "the 'redis' package is required for RedisStore "
                "(pip install redis)"
            ) from exc
        return redis.Redis(**self._options)
