"""Persist what the user arranged in the web UI: node positions, view, search.

The graph itself is rebuilt from its source on every start, so nothing here is
required for the UI to work: the store is a sidecar that lets a reopened page
pick up where it left off.

Files live under ``data/web-layout/<key>.json`` (``--layout-dir`` moves the
directory). The key is derived from the graph source plus its node ids, so two
different graphs never share a file, and a stale file whose nodes disappeared
simply contributes the positions that still match.

The rules mirror the Redis recovery rules in :mod:`compiler.persistence`:
reads never raise, a corrupted file is renamed out of the way instead of being
deleted, and only a failed *write* is reported (``LayoutError``) - the caller
decides whether that is fatal.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: Shape version of the stored JSON; a file with another version is ignored.
LAYOUT_VERSION = 1

#: Where saved layouts go by default, relative to the working directory.
DEFAULT_LAYOUT_DIR = "data/web-layout"

#: Bounds so a broken client cannot fill the disk or store nonsense.
MAX_POSITIONS = 5000
MAX_SEARCH_LENGTH = 200
MAX_COORDINATE = 1.0e6
MIN_ZOOM = 0.05
MAX_ZOOM = 10.0

#: Public keys of a layout state.
STATE_KEYS = ("positions", "view", "search")


class LayoutError(RuntimeError):
    """A layout could not be written (for example: a read-only directory)."""


def layout_key(graph: Any) -> str:
    """Stable identity of a graph: its source plus its sorted node ids."""

    parts = [f"layout={LAYOUT_VERSION}", f"source={graph.metadata.get('source', '')}"]
    parts.extend(f"node={node.id}" for node in sorted(graph.get_nodes(), key=lambda n: n.id))
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def empty_state() -> Dict[str, Any]:
    """The layout of a graph the user has not touched yet."""

    return {"positions": {}, "view": None, "search": ""}


def apply_update(
    state: Dict[str, Any],
    payload: Any,
    *,
    node_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Return a new state: ``payload``'s valid keys applied on top of ``state``.

    Only the keys present in ``payload`` change, so the UI can send just what it
    knows about. ``{"reset": true}`` clears everything. Unknown node ids are
    dropped rather than rejected: a graph may change between runs, and a stale
    file must never keep the UI from loading.
    """

    current = {key: state.get(key) for key in STATE_KEYS}
    if not isinstance(payload, dict):
        return current
    if payload.get("reset"):
        return empty_state()

    allowed = None if node_ids is None else set(node_ids)
    if "positions" in payload and isinstance(payload["positions"], dict):
        current["positions"] = _positions(payload["positions"], allowed)
    if "view" in payload:
        view = payload["view"]
        current["view"] = _view(view) if isinstance(view, dict) else None
    if "search" in payload and isinstance(payload["search"], str):
        current["search"] = payload["search"][:MAX_SEARCH_LENGTH]
    return current


class LayoutStore:
    """JSON sidecar for one graph: atomic writes, tolerant reads."""

    def __init__(
        self,
        directory: Any,
        key: str,
        *,
        node_ids: Optional[Iterable[str]] = None,
        clock: Any = time.time,
    ) -> None:
        self.directory = Path(directory)
        self.key = key
        #: Nodes the graph has right now; positions of anything else are stale.
        self.node_ids: Optional[frozenset] = (
            None if node_ids is None else frozenset(node_ids)
        )
        self._clock = clock
        self._lock = threading.Lock()
        #: What went wrong while reading; the CLI may print these later.
        self.warnings: List[str] = []

    @classmethod
    def for_graph(cls, directory: Any, graph: Any, *, clock: Any = time.time) -> "LayoutStore":
        """Store for the layout of ``graph``, under ``directory``."""

        return cls(
            directory,
            layout_key(graph),
            node_ids=[node.id for node in graph.get_nodes()],
            clock=clock,
        )

    @property
    def path(self) -> Path:
        return self.directory / f"{self.key}.json"

    # ------------------------------------------------------------------
    # Reading / writing
    # ------------------------------------------------------------------
    def load(self) -> Dict[str, Any]:
        """The saved state, or an empty one when there is nothing usable."""

        with self._lock:
            record = self._read(self.path)
        state = apply_update(empty_state(), record or {}, node_ids=self.node_ids)
        state["saved_at"] = record.get("saved_at") if record and not _is_empty(state) else None
        state["persisted"] = True
        return state

    def save(
        self,
        payload: Dict[str, Any],
        *,
        node_ids: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Merge ``payload`` into the saved state and write it atomically."""

        with self._lock:
            allowed = self.node_ids if node_ids is None else node_ids
            current = apply_update(
                empty_state(), self._read(self.path) or {}, node_ids=allowed
            )
            updated = apply_update(current, payload, node_ids=allowed)
            record = {
                "version": LAYOUT_VERSION,
                "key": self.key,
                "saved_at": self._timestamp(),
                **updated,
            }
            self._write(record)
        saved_at = None if _is_empty(updated) else record["saved_at"]
        return {**updated, "saved_at": saved_at, "persisted": True}

    def clear(self) -> Dict[str, Any]:
        """Forget the saved layout (the file keeps an empty record)."""

        return self.save({"reset": True})

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _timestamp(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self._clock()))

    def _warn(self, message: str) -> None:
        self.warnings.append(message)

    def _read(self, path: Path) -> Optional[Dict[str, Any]]:
        """Parse ``path``; a missing or damaged file is "no layout", never an error."""

        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as error:
            self._warn(f"cannot read {path}: {error}")
            return None
        try:
            record = json.loads(raw)
        except ValueError as error:
            self._quarantine(path, f"not valid JSON ({error})")
            return None
        if not isinstance(record, dict):
            self._quarantine(path, "not a JSON object")
            return None
        if record.get("version") != LAYOUT_VERSION:
            self._quarantine(path, f"unknown layout version {record.get('version')!r}")
            return None
        return record

    def _write(self, record: Dict[str, Any]) -> None:
        """Write ``record`` atomically: a reader sees the old or the new file."""

        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise LayoutError(f"cannot create {self.directory}: {error}") from error
        text = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True)
        handle = None
        temporary: Optional[str] = None
        try:
            descriptor, temporary = tempfile.mkstemp(
                dir=str(self.directory), prefix=f".{self.key}-", suffix=".tmp"
            )
            handle = os.fdopen(descriptor, "w", encoding="utf-8")
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            handle = None
            os.replace(temporary, self.path)
            temporary = None
        except OSError as error:
            raise LayoutError(f"cannot write {self.path}: {error}") from error
        finally:
            if handle is not None:
                handle.close()
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:  # pragma: no cover - best effort cleanup
                    pass

    def _quarantine(self, path: Path, reason: str) -> None:
        """Move a damaged file aside; never delete what the user wrote."""

        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self._clock()))
        target = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            os.replace(path, target)
        except OSError as error:
            self._warn(f"{path} is unusable ({reason}) and could not be moved: {error}")
            return
        self._warn(f"{path} is unusable ({reason}); moved to {target.name}")


# ----------------------------------------------------------------------
# Validation helpers
# ----------------------------------------------------------------------
def _is_empty(state: Dict[str, Any]) -> bool:
    """``True`` when there is nothing worth remembering (a cleared layout)."""

    return not state.get("positions") and not state.get("view") and not state.get("search")


def _positions(positions: Dict[str, Any], allowed: Optional[set]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for node_id, point in list(positions.items())[:MAX_POSITIONS]:
        if not isinstance(node_id, str):
            continue
        if allowed is not None and node_id not in allowed:
            continue
        cleaned_point = _point(point)
        if cleaned_point is not None:
            cleaned[node_id] = cleaned_point
    return cleaned


def _point(value: Any) -> Optional[Dict[str, float]]:
    if not isinstance(value, dict):
        return None
    pair = _pair(value.get("x"), value.get("y"))
    if pair is None:
        return None
    return {"x": _round(pair[0]), "y": _round(pair[1])}


def _view(value: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    zoom = _number(value.get("zoom"))
    if zoom is None:
        return None
    zoom = min(max(zoom, MIN_ZOOM), MAX_ZOOM)
    view: Dict[str, Any] = {"zoom": _round(zoom, 4)}
    pan = value.get("pan")
    if isinstance(pan, dict):
        pair = _pair(pan.get("x"), pan.get("y"))
        if pair is not None:
            view["pan"] = {"x": _round(pair[0]), "y": _round(pair[1])}
    return view


def _pair(first: Any, second: Any) -> Optional[Tuple[float, float]]:
    x, y = _number(first), _number(second)
    if x is None or y is None:
        return None
    return x, y


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    if abs(number) > MAX_COORDINATE:
        return None
    return number


def _round(value: float, digits: int = 3) -> float:
    return round(value, digits) + 0.0
