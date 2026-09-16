"""Command line interface: ``python -m compiler example.lw``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

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
    parser.add_argument("source", help="path to a .lw graph source file")
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
    source = Path(args.source)

    if source.suffix.casefold() != SUPPORTED_SUFFIX:
        print(
            f"error: '{source}' is not a .lw graph source; only {SUPPORTED_SUFFIX} "
            "files are supported by this command",
            file=sys.stderr,
        )
        return 2

    quiet = args.quiet or args.json
    if not quiet:
        print(f"Loading {source}...")

    try:
        document = load_lw_file(source)
    except LWError as error:
        print(str(error), file=sys.stderr)
        print(HINT, file=sys.stderr)
        return 2

    graph = to_graph(document, source=str(source))
    if args.json:
        print(json.dumps(graph_payload(graph), ensure_ascii=False, indent=2))
        return 0

    if not quiet:
        print("Mermaid parsed successfully.")
        print(f"Nodes: {len(graph.get_nodes())}")
        print(f"Edges: {len(graph.get_edges())}")

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
