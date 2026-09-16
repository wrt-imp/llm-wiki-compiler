"""``.lw`` file loading tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler.lw import LWFileError, MermaidParseError, load_lw_file

GRAPH = "graph TD\n    A[解析器] -->|produces| B[文档模型]\n"


def test_loads_utf8(tmp_path: Path) -> None:
    path = tmp_path / "graph.lw"
    path.write_bytes(GRAPH.encode("utf-8"))

    document = load_lw_file(path)

    assert document.direction == "TD"
    assert [node.label for node in document.nodes] == ["解析器", "文档模型"]
    assert document.metadata["encoding"] == "utf-8"
    assert document.metadata["had_decoding_errors"] is False
    assert document.source.endswith("graph.lw")


def test_loads_gbk(tmp_path: Path) -> None:
    path = tmp_path / "gbk.lw"
    path.write_bytes(GRAPH.encode("gbk"))

    document = load_lw_file(path)

    assert [node.label for node in document.nodes] == ["解析器", "文档模型"]
    assert document.metadata["encoding"] in {"gbk", "gb18030"}


def test_loads_utf8_with_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.lw"
    path.write_bytes(GRAPH.encode("utf-8-sig"))

    document = load_lw_file(path)

    assert document.direction == "TD"
    assert document.metadata["encoding"] == "utf-8-sig"


def test_missing_file_is_a_file_error(tmp_path: Path) -> None:
    missing = tmp_path / "nope.lw"

    with pytest.raises(LWFileError) as error:
        load_lw_file(missing)

    assert str(missing) in str(error.value)


def test_directory_is_a_file_error(tmp_path: Path) -> None:
    with pytest.raises(LWFileError) as error:
        load_lw_file(tmp_path)

    assert "not a file" in str(error.value)


def test_parse_errors_keep_the_file_name(tmp_path: Path) -> None:
    path = tmp_path / "broken.lw"
    path.write_text("graph TD\n    A --> --> B\n", encoding="utf-8")

    with pytest.raises(MermaidParseError) as error:
        load_lw_file(path)

    assert "broken.lw" in str(error.value)
