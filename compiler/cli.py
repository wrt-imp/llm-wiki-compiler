"""Command line interface: ``python -m compiler example.lw``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .graph import Graph, build_graph
from .knowledge import KnowledgeBase
from .lw import LWError, load_lw_file, to_graph
from .web import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    WebServerError,
    graph_payload,
    serve_graph,
)

#: Suffix of the graph source format this command understands.
SUPPORTED_SUFFIX = ".lw"

HINT = (
    "hint: .lw files use Mermaid graph syntax, for example:\n"
    "  graph TD\n"
    "      Parser[解析器] -->|produces| DocumentModel[文档模型]"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compiler",
        description=(
            "Compile a .lw (Mermaid graph) source into a graph and browse it in "
            "the local web UI."
        ),
    )
    parser.add_argument(
        "source", nargs="?", help="path to a .lw graph source file"
    )
    parser.add_argument(
        "--kb",
        metavar="FILE",
        help=(
            "serve a KnowledgeBase saved as JSON instead of a .lw file "
            "(KnowledgeBase.to_dict() output)"
        ),
    )
    parser.add_argument(
        "--graph-json",
        metavar="FILE",
        help="serve a Graph saved as JSON instead of a .lw file (Graph.to_dict())",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"bind address (default {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"port for the web UI (default {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open a browser"
    )
    parser.add_argument(
        "--check", action="store_true", help="parse and report, without serving"
    )
    parser.add_argument(
        "--json", action="store_true", help="print the graph as JSON and exit"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="only print errors")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI; returns the process exit code."""

    args = build_parser().parse_args(argv)
    quiet = args.quiet or args.json

    provided = [
        name
        for name, value in (
            ("source", args.source),
            ("--kb", args.kb),
            ("--graph-json", args.graph_json),
        )
        if value
    ]
    if len(provided) != 1:
        print(
            "error: provide exactly one input: a .lw file, --kb FILE or "
            "--graph-json FILE",
            file=sys.stderr,
        )
        return 2

    if args.kb:
        graph = _load_knowledge_graph(args.kb, quiet=quiet)
    elif args.graph_json:
        graph = _load_saved_graph(args.graph_json, quiet=quiet)
    else:
        graph = _load_lw_graph(args.source, quiet=quiet)
    if graph is None:
        return 2

    if args.json:
        print(json.dumps(graph_payload(graph), ensure_ascii=False, indent=2))
        return 0

    if args.check:
        return 0

    if not quiet:
        print("Building Graph...")
        print("Starting Web Server...")
    try:
        serve_graph(
            graph,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
        )
    except WebServerError as error:
        print(f"error: {error}", file=sys.stderr)
        return 3
    return 0


def _load_lw_graph(raw_path: str, *, quiet: bool) -> Optional[Graph]:
    """Parse a ``.lw`` (Mermaid) source file into a graph."""

    source = Path(raw_path)
    if source.suffix.casefold() != SUPPORTED_SUFFIX:
        print(
            f"error: '{source}' is not a .lw graph source; only {SUPPORTED_SUFFIX} "
            "files are supported by this command",
            file=sys.stderr,
        )
        return None
    if not quiet:
        print(f"Loading {source}...")
    try:
        document = load_lw_file(source)
    except LWError as error:
        print(str(error), file=sys.stderr)
        print(HINT, file=sys.stderr)
        return None
    graph = to_graph(document, source=str(source))
    if not quiet:
        print("Mermaid parsed successfully.")
        _print_counts(graph)
    return graph


def _load_knowledge_graph(raw_path: str, *, quiet: bool) -> Optional[Graph]:
    """Build a graph from a KnowledgeBase saved as JSON."""

    path = Path(raw_path)
    if not quiet:
        print(f"Loading {path}...")
    data = _read_json(path)
    if data is None:
        return None
    if not any(
        key in data for key in ("entities", "concepts", "facts", "relations")
    ):
        print(
            f"error: '{path}' is not a KnowledgeBase JSON document (it needs at "
            "least one of 'entities', 'concepts', 'facts', 'relations')",
            file=sys.stderr,
        )
        return None
    try:
        knowledge_base = KnowledgeBase.from_dict(data)
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        print(
            f"error: '{path}' is not a KnowledgeBase JSON document ({error})",
            file=sys.stderr,
        )
        return None
    graph = build_graph(knowledge_base)
    graph.metadata.setdefault("source", str(path))
    if not quiet:
        print("KnowledgeBase loaded.")
        _print_counts(graph)
    return graph


def _load_saved_graph(raw_path: str, *, quiet: bool) -> Optional[Graph]:
    """Load a graph that was saved with ``Graph.to_dict()``."""

    path = Path(raw_path)
    if not quiet:
        print(f"Loading {path}...")
    data = _read_json(path)
    if data is None:
        return None
    if "nodes" not in data or "edges" not in data:
        print(
            f"error: '{path}' is not a Graph JSON document (it needs 'nodes' "
            "and 'edges')",
            file=sys.stderr,
        )
        return None
    try:
        graph = Graph.from_dict(data)
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        print(
            f"error: '{path}' is not a Graph JSON document ({error})",
            file=sys.stderr,
        )
        return None
    graph.metadata.setdefault("source", str(path))
    if not quiet:
        print("Graph loaded.")
        _print_counts(graph)
    return graph


def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        print(f"error: file does not exist: '{path}'", file=sys.stderr)
        return None
    if not path.is_file():
        print(f"error: not a file: '{path}'", file=sys.stderr)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        print(f"error: cannot read '{path}': {error}", file=sys.stderr)
        return None
    except json.JSONDecodeError as error:
        print(f"error: '{path}' is not valid JSON: {error}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print(f"error: '{path}' must contain a JSON object", file=sys.stderr)
        return None
    return data


def _print_counts(graph: Graph) -> None:
    print(f"Nodes: {len(graph.get_nodes())}")
    print(f"Edges: {len(graph.get_edges())}")
