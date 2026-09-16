"""Local web UI for browsing a graph: ``http://localhost:63333``.

The UI is one static page plus ``GET /api/graph``; the server uses only the
standard library. Graph visualization uses cytoscape.js from a CDN, with a
plain text fallback when the import fails (for example while offline).
"""

from .server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    STATIC_DIR,
    WebServerError,
    create_server,
    graph_payload,
    serve_graph,
)

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "STATIC_DIR",
    "WebServerError",
    "create_server",
    "graph_payload",
    "serve_graph",
]
