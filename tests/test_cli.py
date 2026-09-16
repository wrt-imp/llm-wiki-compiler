"""CLI tests: ``python -m compiler example.lw``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler.cli import main
from support import entity, make_kb, relation, src_ref

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "example.lw"


def test_check_mode_reports_the_graph(capsys: pytest.CaptureFixture) -> None:
    assert main(["--check", str(EXAMPLE)]) == 0

    out = capsys.readouterr().out
    assert f"Loading {EXAMPLE}..." in out
    assert "Mermaid parsed successfully." in out
    assert "Nodes: 3" in out
    assert "Edges: 2" in out


def test_json_mode_prints_only_json(capsys: pytest.CaptureFixture) -> None:
    assert main(["--json", str(EXAMPLE)]) == 0

    data = json.loads(capsys.readouterr().out)
    assert [node["id"] for node in data["nodes"]] == ["AST", "DocumentModel", "Parser"]
    assert len(data["edges"]) == 2
    assert data["metadata"]["source"].endswith("example.lw")
    assert data["metadata"]["direction"] == "TD"


def test_quiet_mode_prints_nothing(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["--check", "-q", str(EXAMPLE)]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_parse_errors_show_file_line_and_column(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    broken = tmp_path / "broken.lw"
    broken.write_text("graph TD\n    A --> --> B\n", encoding="utf-8")

    assert main([str(broken)]) == 2

    err = capsys.readouterr().err
    assert f"ParseError: {broken}:2:" in err
    assert "Invalid Mermaid graph syntax" in err
    assert "hint:" in err


def test_missing_file_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert main([str(tmp_path / "nope.lw")]) == 2

    assert "does not exist" in capsys.readouterr().err


def test_non_lw_input_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    other = tmp_path / "notes.md"
    other.write_text("# nope\n", encoding="utf-8")

    assert main([str(other)]) == 2

    assert "only .lw files" in capsys.readouterr().err


def test_help_exits_zero(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--help"])

    assert error.value.code == 0
    assert "usage: compiler" in capsys.readouterr().out


def test_serve_options_are_forwarded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    calls = {}

    def fake_serve(graph, **options):
        calls["graph"] = graph
        calls.update(options)

    monkeypatch.setattr("compiler.cli.serve_graph", fake_serve)

    assert main([str(EXAMPLE), "--port", "64999", "--host", "127.0.0.1", "--no-browser"]) == 0

    assert calls["port"] == 64999
    assert calls["host"] == "127.0.0.1"
    assert calls["open_browser"] is False
    assert len(calls["graph"].get_nodes()) == 3


def test_browser_is_opened_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {}

    def fake_serve(graph, **options):
        calls.update(options)

    monkeypatch.setattr("compiler.cli.serve_graph", fake_serve)

    assert main(["--quiet", str(EXAMPLE)]) == 0

    assert calls["open_browser"] is True


def write_knowledge_base(tmp_path: Path) -> Path:
    kb = make_kb(
        entities=(
            entity(
                "解析器",
                type="system",
                aliases=("Parser",),
                sources=(src_ref("docA", quote="解析器"),),
            ),
            entity("文档模型", sources=(src_ref("docA", quote="文档模型"),)),
        ),
        relations=(
            relation(
                "解析器", "文档模型", type="produces", sources=(src_ref("docA"),)
            ),
        ),
    )
    path = tmp_path / "knowledge_base.json"
    path.write_text(
        json.dumps(kb.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    return path


def test_knowledge_base_json_is_served(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    path = write_knowledge_base(tmp_path)
    calls = {}

    def fake_serve(graph, **options):
        calls["graph"] = graph
        calls.update(options)

    monkeypatch.setattr("compiler.cli.serve_graph", fake_serve)

    assert main(["--kb", str(path)]) == 0

    out = capsys.readouterr().out
    assert "KnowledgeBase loaded." in out
    assert "Nodes: 2" in out
    assert "Edges: 1" in out
    assert [node.title for node in calls["graph"].get_nodes()] == ["文档模型", "解析器"]
    assert calls["graph"].metadata["source"] == str(path)
    assert calls["open_browser"] is True


def test_saved_graph_json_is_served(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    from compiler.graph import Graph, build_graph
    from compiler.knowledge import KnowledgeBase

    kb_path = write_knowledge_base(tmp_path)
    kb = KnowledgeBase.from_dict(json.loads(kb_path.read_text(encoding="utf-8")))
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(build_graph(kb).to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    calls = {}

    def fake_serve(graph, **options):
        calls["graph"] = graph

    monkeypatch.setattr("compiler.cli.serve_graph", fake_serve)

    assert main(["--graph-json", str(graph_path), "--quiet"]) == 0

    assert isinstance(calls["graph"], Graph)
    assert len(calls["graph"].get_edges()) == 1
    assert capsys.readouterr().out == ""


def test_json_mode_works_with_a_knowledge_base(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    path = write_knowledge_base(tmp_path)

    assert main(["--kb", str(path), "--json"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert [node["title"] for node in data["nodes"]] == ["文档模型", "解析器"]
    assert data["edges"][0]["type"] == "produces"
    assert data["metadata"]["source"] == str(path)


def test_check_mode_works_with_a_knowledge_base(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    path = write_knowledge_base(tmp_path)

    assert main(["--kb", str(path), "--check"]) == 0

    out = capsys.readouterr().out
    assert "Nodes: 2" in out and "Edges: 1" in out


def test_missing_knowledge_base_file_returns_two(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["--kb", str(tmp_path / "nope.json")]) == 2

    assert "does not exist" in capsys.readouterr().err


def test_invalid_json_file_returns_two(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    assert main(["--kb", str(broken)]) == 2

    assert "not valid JSON" in capsys.readouterr().err


def test_json_with_the_wrong_shape_returns_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"entities": "not a list"}), encoding="utf-8")
    served = []
    monkeypatch.setattr(
        "compiler.cli.serve_graph", lambda graph, **options: served.append(graph)
    )

    assert main(["--graph-json", str(wrong)]) == 2

    assert "is not a Graph JSON document" in capsys.readouterr().err
    assert served == []


def test_knowledge_base_json_with_the_wrong_shape_returns_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    served = []
    monkeypatch.setattr(
        "compiler.cli.serve_graph", lambda graph, **options: served.append(graph)
    )

    assert main(["--kb", str(wrong)]) == 2

    assert "is not a KnowledgeBase JSON document" in capsys.readouterr().err
    assert served == []


def test_exactly_one_input_is_required(capsys: pytest.CaptureFixture, tmp_path: Path) -> None:
    assert main([]) == 2
    assert "exactly one input" in capsys.readouterr().err

    both = ["--kb", str(write_knowledge_base(tmp_path)), str(EXAMPLE)]
    assert main(both) == 2
    assert "exactly one input" in capsys.readouterr().err
