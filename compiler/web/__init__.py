"""Local web UI for browsing a graph: ``http://localhost:63333``.

The UI is one static page plus ``GET /api/graph`` and ``/api/layout``; the
server uses only the standard library. Graph visualization uses cytoscape.js
from a CDN, with a plain text fallback when the import fails (for example while
offline). ``/api/layout`` persists what the user arranged (node positions,
zoom/pan, search) through :class:`~compiler.web.layout.LayoutStore`.
"""

from .layout import (
    DEFAULT_LAYOUT_DIR,
    LayoutError,
    LayoutStore,
    empty_state,
    layout_key,
)
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
    "DEFAULT_LAYOUT_DIR",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "STATIC_DIR",
    "LayoutError",
    "LayoutStore",
    "WebServerError",
    "create_server",
    "empty_state",
    "graph_payload",
    "layout_key",
    "serve_graph",
]
