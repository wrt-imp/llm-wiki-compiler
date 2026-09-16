"""CLI tests: ``python -m compiler example.lw``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler.cli import main

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
