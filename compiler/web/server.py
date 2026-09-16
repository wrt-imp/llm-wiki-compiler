"""A tiny local web server for browsing a :class:`~compiler.graph.Graph`.

Standard library only: ``GET /`` serves the UI, ``GET /api/graph`` returns the
graph as JSON. The graph is parsed once at startup and kept in memory, so the
server never touches the source files again.
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from ..graph import Graph

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 63333

STATIC_DIR = Path(__file__).resolve().parent / "static"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}
_STATIC_ROUTES = {
    "/static/app.js": "app.js",
    "/static/style.css": "style.css",
}


class WebServerError(RuntimeError):
    """The server could not be started (for example the port is taken)."""


def graph_payload(graph: Graph) -> Dict[str, Any]:
    """JSON friendly view of a graph, used by ``GET /api/graph``."""

    return {
        "nodes": [node.to_dict() for node in graph.get_nodes()],
        "edges": [edge.to_dict() for edge in graph.get_edges()],
        "metadata": dict(graph.metadata),
    }


def create_server(
    graph: Graph,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    """Build (but do not start) the HTTP server for ``graph``."""

    handler = _handler_for(graph)
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
) -> None:
    """Serve ``graph`` until interrupted, optionally opening a browser."""

    server = create_server(graph, host=host, port=port)
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


def _handler_for(graph: Graph) -> type:
    payload = graph_payload(graph)

    class GraphRequestHandler(_GraphRequestHandler):
        _payload = payload

    GraphRequestHandler.__name__ = "GraphRequestHandler"
    return GraphRequestHandler


class _GraphRequestHandler(BaseHTTPRequestHandler):
    """Routes: ``/``, ``/static/*`` and ``/api/graph``."""

    _payload: Dict[str, Any] = {"nodes": [], "edges": [], "metadata": {}}
    server_version = "llm-wiki-compiler"

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html")
            return
        if path == "/api/graph":
            self._send_json(self._payload)
            return
        if path in _STATIC_ROUTES:
            self._send_file(STATIC_DIR / _STATIC_ROUTES[path])
            return
        self._send_text(404, "404 Not Found\n")

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
