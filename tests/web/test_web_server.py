"""Web server tests: ``GET /``, ``/api/graph`` and static assets."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Iterator, Tuple

import pytest

from compiler.lw import parse_mermaid, to_graph
from compiler.web import (
    WebServerError,
    create_server,
    graph_payload,
    serve_graph,
)
from compiler.web.server import static_file

SOURCE = "graph TD\n    Parser[解析器] -->|produces| DocumentModel[文档模型]\n"


def sample_graph():
    return to_graph(parse_mermaid(SOURCE, source="example.lw"), source="example.lw")


def fetch(url: str) -> Tuple[int, str, bytes]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.headers.get("Content-Type", ""), response.read()


@pytest.fixture
def server_url() -> Iterator[Tuple[object, str]]:
    graph = sample_graph()
    server = create_server(graph, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield graph, f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_index_is_served(server_url) -> None:
    _, url = server_url

    status, content_type, body = fetch(url + "/")

    assert status == 200
    assert "text/html" in content_type
    assert b"LLM Wiki Compiler" in body
    assert b"/static/app.js" in body
    assert b"/api/graph" in body or b"app.js" in body


def test_api_graph_returns_the_graph(server_url) -> None:
    graph, url = server_url

    status, content_type, body = fetch(url + "/api/graph")
    data = json.loads(body.decode("utf-8"))

    assert status == 200
    assert "application/json" in content_type
    assert [node["id"] for node in data["nodes"]] == ["DocumentModel", "Parser"]
    assert data["edges"][0]["type"] == "produces"
    assert data["metadata"]["direction"] == "TD"
    assert data == {
        "nodes": [node.to_dict() for node in graph.get_nodes()],
        "edges": [edge.to_dict() for edge in graph.get_edges()],
        "metadata": dict(graph.metadata),
    }


def test_static_assets_are_served(server_url) -> None:
    _, url = server_url

    js_status, js_type, js_body = fetch(url + "/static/app.js")
    css_status, css_type, _ = fetch(url + "/static/style.css")

    assert js_status == 200 and "javascript" in js_type
    assert b"cytoscape" in js_body
    assert css_status == 200 and "css" in css_type


def test_vendored_graph_libraries_are_served(server_url) -> None:
    """The page must not depend on a CDN: the libraries live in static/vendor/."""

    _, url = server_url

    for name, needle in (
        ("cytoscape.min.js", b"cytoscape"),
        ("dagre.min.js", b"dagre"),
        ("cytoscape-dagre.js", b"cytoscapeDagre"),
    ):
        status, content_type, body = fetch(f"{url}/static/vendor/{name}")
        assert status == 200, name
        assert "javascript" in content_type, name
        assert needle in body, name


def test_static_file_stays_inside_the_static_directory() -> None:
    assert static_file("/static/app.js") is not None
    assert static_file("/static/vendor/cytoscape.min.js") is not None

    for path in (
        "/static/",
        "/static",
        "/static/nope.js",
        "/static/../server.py",
        "/static/%2e%2e/server.py",
        "/static/vendor/../../server.py",
        "/api/graph",
        "/",
    ):
        assert static_file(path) is None, path


def test_unknown_path_returns_404(server_url) -> None:
    _, url = server_url

    with pytest.raises(urllib.error.HTTPError) as error:
        fetch(url + "/nope")

    assert error.value.code == 404


def test_graph_payload_shape() -> None:
    payload = graph_payload(sample_graph())

    assert set(payload) == {"nodes", "edges", "metadata"}
    assert payload["metadata"]["source"] == "example.lw"


def test_invalid_host_is_reported_as_a_server_error() -> None:
    with pytest.raises(WebServerError):
        create_server(sample_graph(), host="999.999.999.999", port=63333)


def test_serve_graph_opens_the_browser(monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(
        "compiler.web.server.webbrowser.open", lambda url: opened.append(url)
    )

    def stop(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "compiler.web.server.ThreadingHTTPServer.serve_forever", stop
    )

    serve_graph(sample_graph(), port=0, printer=lambda *_: None)

    assert opened and opened[0].startswith("http://127.0.0.1:")


def test_serve_graph_can_skip_the_browser(monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(
        "compiler.web.server.webbrowser.open", lambda url: opened.append(url)
    )

    def stop(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "compiler.web.server.ThreadingHTTPServer.serve_forever", stop
    )

    serve_graph(sample_graph(), port=0, open_browser=False, printer=lambda *_: None)

    assert opened == []
