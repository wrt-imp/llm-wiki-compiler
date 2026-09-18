"""Layout persistence: the JSON store and the ``/api/layout`` endpoints."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, Optional, Tuple

import pytest

from compiler.lw import parse_mermaid, to_graph
from compiler.web import LayoutStore, create_server, layout_key
from compiler.web.layout import LAYOUT_VERSION, LayoutError
from compiler.web.server import MAX_BODY_BYTES

SOURCE = "graph TD\n    Parser[解析器] -->|produces| DocumentModel[文档模型]\n"


def sample_graph(source: str = "example.lw"):
    return to_graph(parse_mermaid(SOURCE, source=source), source=source)


def make_store(directory) -> LayoutStore:
    return LayoutStore.for_graph(directory, sample_graph())


# ----------------------------------------------------------------------
# The store
# ----------------------------------------------------------------------
def test_key_follows_the_source_and_the_nodes() -> None:
    assert layout_key(sample_graph()) == layout_key(sample_graph())
    assert layout_key(sample_graph("other.lw")) != layout_key(sample_graph())
    assert layout_key(sample_graph()) == layout_key(sample_graph("example.lw"))


def test_loading_without_a_file_gives_an_empty_state(tmp_path) -> None:
    state = make_store(tmp_path).load()

    assert state["positions"] == {}
    assert state["view"] is None
    assert state["search"] == ""
    assert state["saved_at"] is None
    assert state["persisted"] is True


def test_save_then_load_round_trips(tmp_path) -> None:
    layout = make_store(tmp_path)
    saved = layout.save(
        {
            "positions": {"Parser": {"x": 12.5, "y": -30}},
            "view": {"zoom": 1.25, "pan": {"x": 7, "y": 8}},
            "search": "par",
        }
    )

    state = layout.load()
    assert saved["saved_at"] == state["saved_at"]
    assert state["positions"] == {"Parser": {"x": 12.5, "y": -30.0}}
    assert state["view"] == {"zoom": 1.25, "pan": {"x": 7.0, "y": 8.0}}
    assert state["search"] == "par"
    assert layout.path.exists()


def test_a_partial_update_keeps_what_was_saved_before(tmp_path) -> None:
    layout = make_store(tmp_path)
    layout.save({"positions": {"Parser": {"x": 1, "y": 2}}})
    layout.save({"search": "doc"})

    state = layout.load()
    assert state["positions"] == {"Parser": {"x": 1.0, "y": 2.0}}
    assert state["search"] == "doc"


def test_unknown_nodes_and_broken_values_are_dropped(tmp_path) -> None:
    layout = make_store(tmp_path)
    layout.save(
        {
            "positions": {
                "Parser": {"x": 1, "y": 2},
                "Ghost": {"x": 3, "y": 4},
                "Broken": "not a point",
                "DocumentModel": {"x": "nope", "y": 0},
            },
            "view": {"zoom": "big"},
            "search": 42,
        }
    )

    state = layout.load()
    assert list(state["positions"]) == ["Parser"]
    assert state["view"] is None
    assert state["search"] == ""


def test_view_is_clamped_to_sane_zoom(tmp_path) -> None:
    layout = make_store(tmp_path)

    assert layout.save({"view": {"zoom": 1000}})["view"]["zoom"] == 10.0
    assert layout.save({"view": {"zoom": 0.0001}})["view"]["zoom"] == 0.05
    assert layout.save({"view": None})["view"] is None


def test_a_long_search_is_truncated(tmp_path) -> None:
    layout = make_store(tmp_path)

    state = layout.save({"search": "x" * 500})

    assert len(state["search"]) == 200


def test_reset_forgets_everything(tmp_path) -> None:
    layout = make_store(tmp_path)
    layout.save({"positions": {"Parser": {"x": 1, "y": 2}}, "search": "par"})

    state = layout.clear()

    assert state["positions"] == {} and state["search"] == ""
    assert layout.load()["positions"] == {}


def test_a_cleared_layout_reports_no_timestamp(tmp_path) -> None:
    """An empty record means "nothing saved", not "saved a moment ago"."""

    layout = make_store(tmp_path)
    layout.save({"positions": {"Parser": {"x": 1, "y": 2}}})
    assert layout.load()["saved_at"]

    assert layout.clear()["saved_at"] is None
    assert layout.load()["saved_at"] is None


def test_a_corrupted_file_is_moved_aside_not_deleted(tmp_path) -> None:
    layout = make_store(tmp_path)
    layout.save({"positions": {"Parser": {"x": 1, "y": 2}}})
    layout.path.write_text("{ this is not json", encoding="utf-8")

    state = layout.load()

    assert state["positions"] == {}
    assert layout.warnings, "the user should be able to see why it was ignored"
    quarantined = list(tmp_path.glob("*.corrupt-*"))
    assert len(quarantined) == 1
    assert not layout.path.exists()


def test_a_file_from_another_version_is_ignored(tmp_path) -> None:
    layout = make_store(tmp_path)
    layout.path.parent.mkdir(parents=True, exist_ok=True)
    layout.path.write_text(
        json.dumps({"version": LAYOUT_VERSION + 1, "positions": {"Parser": {"x": 1, "y": 2}}}),
        encoding="utf-8",
    )

    assert layout.load()["positions"] == {}
    assert list(tmp_path.glob("*.corrupt-*"))


def test_writing_is_atomic_and_leaves_no_temporary_files(tmp_path) -> None:
    layout = make_store(tmp_path)
    layout.save({"positions": {"Parser": {"x": 1, "y": 2}}})

    assert json.loads(layout.path.read_text(encoding="utf-8"))["version"] == LAYOUT_VERSION
    assert list(tmp_path.glob(".*tmp")) == []


def test_a_broken_directory_reports_a_write_error_without_breaking_reads(tmp_path) -> None:
    blocking = tmp_path / "blocking"
    blocking.write_text("not a directory", encoding="utf-8")
    layout = LayoutStore(blocking / "layouts", "key")

    assert layout.load()["positions"] == {}
    with pytest.raises(LayoutError):
        layout.save({"positions": {"Parser": {"x": 1, "y": 2}}})


# ----------------------------------------------------------------------
# The endpoints
# ----------------------------------------------------------------------
def call(url: str, *, method: str = "GET", payload: Optional[Any] = None, raw: Optional[bytes] = None):
    data = raw
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read()


def serve(graph, *, layout) -> Iterator[str]:
    server = create_server(graph, port=0, layout=layout)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def layout_url(tmp_path) -> Iterator[Tuple[LayoutStore, str]]:
    layout = make_store(tmp_path)
    for url in serve(sample_graph(), layout=layout):
        yield layout, url


def test_get_layout_starts_empty(layout_url) -> None:
    _, url = layout_url

    status, body = call(url + "/api/layout")
    state = json.loads(body)

    assert status == 200
    assert state["positions"] == {} and state["saved_at"] is None
    assert state["persisted"] is True


def test_post_layout_is_visible_to_the_next_get(layout_url) -> None:
    _, url = layout_url

    status, body = call(
        url + "/api/layout",
        method="POST",
        payload={
            "positions": {"Parser": {"x": 5, "y": 6}},
            "view": {"zoom": 2, "pan": {"x": 1, "y": 1}},
            "search": "par",
        },
    )
    saved = json.loads(body)
    _, reread = call(url + "/api/layout")
    state = json.loads(reread)

    assert status == 200 and saved["saved_at"]
    assert state["positions"] == {"Parser": {"x": 5.0, "y": 6.0}}
    assert state["search"] == "par"


def test_post_drops_positions_of_unknown_nodes(layout_url) -> None:
    _, url = layout_url

    _, body = call(
        url + "/api/layout",
        method="POST",
        payload={"positions": {"Parser": {"x": 1, "y": 1}, "Ghost": {"x": 2, "y": 2}}},
    )

    assert list(json.loads(body)["positions"]) == ["Parser"]


def test_post_rejects_a_body_that_is_not_json(layout_url) -> None:
    _, url = layout_url

    with pytest.raises(urllib.error.HTTPError) as error:
        call(url + "/api/layout", method="POST", raw=b"{not json")

    assert error.value.code == 400
    assert "error" in json.loads(error.value.read())


def test_post_rejects_a_body_that_is_not_an_object(layout_url) -> None:
    _, url = layout_url

    with pytest.raises(urllib.error.HTTPError) as error:
        call(url + "/api/layout", method="POST", payload=[1, 2, 3])

    assert error.value.code == 400


def test_post_rejects_an_oversized_body(layout_url) -> None:
    _, url = layout_url

    with pytest.raises(urllib.error.HTTPError) as error:
        call(url + "/api/layout", method="POST", raw=b"x" * (MAX_BODY_BYTES + 1))

    assert error.value.code == 413


def test_post_to_an_unknown_path_is_404(layout_url) -> None:
    _, url = layout_url

    with pytest.raises(urllib.error.HTTPError) as error:
        call(url + "/nope", method="POST", payload={})

    assert error.value.code == 404


def test_reset_clears_the_saved_layout(layout_url) -> None:
    _, url = layout_url
    call(url + "/api/layout", method="POST", payload={"positions": {"Parser": {"x": 9, "y": 9}}})

    _, body = call(url + "/api/layout", method="POST", payload={"reset": True})

    assert json.loads(body)["positions"] == {}


def test_a_restart_keeps_the_layout(tmp_path) -> None:
    """The point of the feature: close the server, start it again, keep arranging."""

    first = make_store(tmp_path)
    for url in serve(sample_graph(), layout=first):
        call(url + "/api/layout", method="POST", payload={"positions": {"Parser": {"x": 42, "y": 24}}})

    second = make_store(tmp_path)
    for url in serve(sample_graph(), layout=second):
        _, body = call(url + "/api/layout")
        assert json.loads(body)["positions"] == {"Parser": {"x": 42.0, "y": 24.0}}


def test_without_a_store_the_endpoints_do_not_persist() -> None:
    for url in serve(sample_graph(), layout=None):
        _, body = call(url + "/api/layout", method="POST", payload={"search": "par"})
        assert json.loads(body)["persisted"] is False
        _, reread = call(url + "/api/layout")
        assert json.loads(reread)["search"] == ""
