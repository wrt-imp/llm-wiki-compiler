"""A tiny local web server for browsing a :class:`~compiler.graph.Graph`.

Standard library only: ``GET /`` serves the UI, ``GET /api/graph`` returns the
graph as JSON. The graph is parsed once at startup and kept in memory, so the
server never touches the source files again.

``GET /api/layout`` and ``POST /api/layout`` read and write what the user
arranged in the UI (node positions, zoom/pan, search box) through a
:class:`~compiler.web.layout.LayoutStore`. Without a store the endpoints still
answer, they just report ``persisted: false`` and forget everything.
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional
from urllib.parse import unquote, urlparse

from ..graph import Graph
from .layout import LayoutError, LayoutStore, empty_state

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 63333

#: Biggest ``POST /api/layout`` body we accept (a graph with thousands of nodes).
MAX_BODY_BYTES = 64 * 1024

#: How much of an over-sized body we swallow before answering, so the client can
#: read the 413 instead of seeing its upload aborted mid-flight.
MAX_DRAIN_BYTES = 4 * 1024 * 1024

STATIC_DIR = Path(__file__).resolve().parent / "static"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}

#: Everything under this URL prefix is served from :data:`STATIC_DIR`.
_STATIC_PREFIX = "/static/"


class WebServerError(RuntimeError):
    """The server could not be started (for example the port is taken)."""


def graph_payload(graph: Graph) -> Dict[str, Any]:
    """JSON friendly view of a graph, used by ``GET /api/graph``."""

    return {
        "nodes": [node.to_dict() for node in graph.get_nodes()],
        "edges": [edge.to_dict() for edge in graph.get_edges()],
        "metadata": dict(graph.metadata),
    }


def static_file(url_path: str) -> Optional[Path]:
    """File under :data:`STATIC_DIR` for a ``/static/...`` URL, else ``None``.

    Serving the whole directory (not a fixed list) lets the vendored graph
    libraries live in ``static/vendor/``. Anything that escapes the directory -
    ``/static/../server.py`` or an encoded equivalent - resolves to ``None``.
    """

    if not url_path.startswith(_STATIC_PREFIX):
        return None
    relative = unquote(url_path[len(_STATIC_PREFIX) :])
    if not relative or relative.endswith("/"):
        return None
    candidate = (STATIC_DIR / relative).resolve()
    root = STATIC_DIR.resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def create_server(
    graph: Graph,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    layout: Optional[LayoutStore] = None,
) -> ThreadingHTTPServer:
    """Build (but do not start) the HTTP server for ``graph``."""

    handler = _handler_for(graph, layout)
    try:
        return ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise WebServerError(
            f"cannot start the web server on {host}:{port}: {exc}"
        ) from exc


def serve_graph(
    graph: Graph,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    printer: Any = print,
    layout: Optional[LayoutStore] = None,
) -> None:
    """Serve ``graph`` until interrupted, optionally opening a browser."""

    server = create_server(graph, host=host, port=port, layout=layout)
    url = f"http://{host}:{port}"
    printer(f"Web UI:\n{url}")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # pragma: no cover - opening a browser is best effort
            printer(f"(could not open a browser automatically; visit {url})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        printer("")
        printer("Stopping web server.")
    finally:
        server.server_close()


def _handler_for(graph: Graph, layout: Optional[LayoutStore] = None) -> type:
    payload = graph_payload(graph)

    class GraphRequestHandler(_GraphRequestHandler):
        _payload = payload
        _layout = layout
        _node_ids = frozenset(node.id for node in graph.get_nodes())

    GraphRequestHandler.__name__ = "GraphRequestHandler"
    return GraphRequestHandler


class _GraphRequestHandler(BaseHTTPRequestHandler):
    """Routes: ``/``, ``/static/*``, ``/api/graph`` and ``/api/layout``."""

    _payload: Dict[str, Any] = {"nodes": [], "edges": [], "metadata": {}}
    _layout: Optional[LayoutStore] = None
    _node_ids: FrozenSet[str] = frozenset()
    server_version = "llm-wiki-compiler"

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html")
            return
        if path == "/api/graph":
            self._send_json(self._payload)
            return
        if path == "/api/layout":
            self._send_json(self._layout_state())
            return
        asset = static_file(path)
        if asset is not None:
            self._send_file(asset)
            return
        self._send_text(404, "404 Not Found\n")

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        # The body is read (and discarded) even for unknown paths: replying
        # before the client finished writing would abort the connection.
        body = self._read_body()
        if body is None:  # already answered (too large)
            return
        if urlparse(self.path).path != "/api/layout":
            self._send_text(404, "404 Not Found\n")
            return
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, ValueError) as error:
            self._send_json_error(400, f"body is not valid JSON: {error}")
            return
        if not isinstance(payload, dict):
            self._send_json_error(400, "body must be a JSON object")
            return
        if self._layout is None:
            self._send_json({**empty_state(), "saved_at": None, "persisted": False})
            return
        try:
            state = self._layout.save(payload, node_ids=self._node_ids)
        except LayoutError as error:
            self._send_json_error(500, str(error))
            return
        self._send_json(state)

    def _layout_state(self) -> Dict[str, Any]:
        if self._layout is None:
            return {**empty_state(), "saved_at": None, "persisted": False}
        try:
            return self._layout.load()
        except Exception as error:  # pragma: no cover - load() is already tolerant
            return {**empty_state(), "saved_at": None, "persisted": False, "error": str(error)}

    def _read_body(self) -> Optional[bytes]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json_error(400, "invalid Content-Length")
            return None
        if length > MAX_BODY_BYTES:
            self._drain(min(length, MAX_DRAIN_BYTES))
            self._send_json_error(413, f"body larger than {MAX_BODY_BYTES} bytes")
            return None
        return self.rfile.read(length) if length > 0 else b""

    def _drain(self, length: int) -> None:
        """Read and throw away ``length`` bytes the client already sent."""

        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def _send_json_error(self, status: int, message: str) -> None:
        self._respond(
            status,
            "application/json; charset=utf-8",
            json.dumps({"error": message}, ensure_ascii=False).encode("utf-8"),
        )

    def _send_file(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self._send_text(500, f"500 missing asset: {path.name}\n")
            return
        self._respond(
            200, _CONTENT_TYPES.get(path.suffix, "application/octet-stream"), data
        )

    def _send_json(self, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._respond(200, "application/json; charset=utf-8", data)

    def _send_text(self, status: int, text: str) -> None:
        self._respond(status, "text/plain; charset=utf-8", text.encode("utf-8"))

    def _respond(self, status: int, content_type: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        """Stay quiet: the CLI prints what matters."""
