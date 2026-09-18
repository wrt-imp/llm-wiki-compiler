"""Command line interface: ``python -m compiler example.lw``.

Three kinds of input are supported: a ``.lw`` (Mermaid) graph source, a
``KnowledgeBase`` JSON file, or a ``Graph`` JSON file. The ``--redis-*`` options
add the optional Redis persistence features (RDB + AOF): a startup health check
and loading/storing artefacts. The web UI always persists the layout the user
arranged (node positions, zoom/pan, search) unless ``--no-layout`` is given.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .graph import Graph, build_graph
from .knowledge import KnowledgeBase
from .lw import LWError, load_lw_file, to_graph
from .persistence import PersistenceError, PersistenceManager, RedisStore
from .web import (
    DEFAULT_LAYOUT_DIR,
    DEFAULT_HOST,
    DEFAULT_PORT,
    LayoutStore,
    WebServerError,
    graph_payload,
    serve_graph,
)

#: Suffix of the graph source format this command understands.
SUPPORTED_SUFFIX = ".lw"

#: Where the managed Redis keeps its files (see scripts/redis-persistence.sh).
DEFAULT_REDIS_DATA_DIR = "data/redis"

HINT = (
    "hint: .lw files use Mermaid graph syntax, for example:\n"
    "  graph TD\n"
    "      Parser[解析器] -->|produces| DocumentModel[文档模型]"
)


@dataclass
class _Loaded:
    """What an input produced."""

    graph: Graph
    knowledge_base: Optional[KnowledgeBase] = None
    label: str = ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compiler",
        description=(
            "Compile a .lw (Mermaid graph) source, a KnowledgeBase JSON or a "
            "Graph JSON into a graph and browse it in the local web UI."
        ),
    )
    parser.add_argument("source", nargs="?", help="path to a .lw graph source file")
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

    web = parser.add_argument_group("web UI")
    web.add_argument(
        "--layout-dir",
        default=DEFAULT_LAYOUT_DIR,
        metavar="DIR",
        help=(
            "where the web UI saves the layout you arrange "
            f"(default {DEFAULT_LAYOUT_DIR})"
        ),
    )
    web.add_argument(
        "--no-layout",
        action="store_true",
        help="do not save the web UI layout between runs",
    )

    redis = parser.add_argument_group("redis persistence")
    redis.add_argument(
        "--redis-check",
        action="store_true",
        help=(
            "check the Redis RDB/AOF files, quarantine a corrupted AOF and "
            "report what to expect (never starts Redis, never crashes)"
        ),
    )
    redis.add_argument(
        "--redis-load",
        metavar="KEY",
        help="load the KnowledgeBase stored under KEY in Redis (instead of a file)",
    )
    redis.add_argument(
        "--redis-save",
        metavar="KEY",
        help="after loading, store the graph (and the KnowledgeBase) in Redis",
    )
    redis.add_argument(
        "--redis-data-dir",
        default=DEFAULT_REDIS_DATA_DIR,
        help=(
            "directory holding dump.rdb / the AOF "
            f"(default {DEFAULT_REDIS_DATA_DIR})"
        ),
    )
    redis.add_argument(
        "--redis-strict",
        action="store_true",
        help="with --redis-check: exit 2 when persistence could not be verified",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI; returns the process exit code."""

    args = build_parser().parse_args(argv)
    quiet = args.quiet or args.json

    if args.redis_check:
        return _run_redis_check(args, quiet=quiet)

    provided = [
        name
        for name, value in (
            ("source", args.source),
            ("--kb", args.kb),
            ("--graph-json", args.graph_json),
            ("--redis-load", args.redis_load),
        )
        if value
    ]
    if len(provided) != 1:
        print(
            "error: provide exactly one input: a .lw file, --kb FILE, "
            "--graph-json FILE or --redis-load KEY",
            file=sys.stderr,
        )
        return 2

    loaded: Optional[_Loaded]
    if args.redis_load:
        loaded = _load_from_redis(args.redis_load, quiet=quiet)
    elif args.kb:
        loaded = _load_knowledge_graph(args.kb, quiet=quiet)
    elif args.graph_json:
        loaded = _load_saved_graph(args.graph_json, quiet=quiet)
    else:
        loaded = _load_lw_graph(args.source, quiet=quiet)
    if loaded is None:
        return 2
    graph = loaded.graph

    if args.redis_save and not _save_to_redis(loaded, args.redis_save, quiet=quiet):
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
        layout = None if args.no_layout else LayoutStore.for_graph(args.layout_dir, graph)
        serve_graph(
            graph,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            layout=layout,
        )
    except WebServerError as error:
        print(f"error: {error}", file=sys.stderr)
        return 3
    return 0


# ----------------------------------------------------------------------
# Redis persistence
# ----------------------------------------------------------------------
def _run_redis_check(args: argparse.Namespace, *, quiet: bool) -> int:
    manager = PersistenceManager(args.redis_data_dir, strict=args.redis_strict)
    report = manager.ensure()
    if not quiet:
        for line in report.log_lines():
            print(line)
        print()
        print(f"data directory : {report.data_dir}")
        print(f"AOF            : {report.aof.status.value if report.aof else 'unknown'}")
        print(f"RDB            : {report.rdb.status.value if report.rdb else 'unknown'}")
        print(f"recovery       : {report.action}")
        print(f"data source    : {report.source}")
        print(f"usable         : {report.usable}")
    if not report.usable:
        print(
            "error: Redis persistence could not be prepared; see the log above",
            file=sys.stderr,
        )
        return 2
    return 0


def _load_from_redis(key: str, *, quiet: bool) -> Optional[_Loaded]:
    if not quiet:
        print(f"Loading KnowledgeBase '{key}' from Redis...")
    try:
        store = RedisStore()
        knowledge_base = store.load_knowledge_base(key)
    except PersistenceError as error:
        print(f"error: {error}", file=sys.stderr)
        return None
    except Exception as error:  # connection problems, bad payload, ...
        print(f"error: cannot read '{key}' from Redis: {error}", file=sys.stderr)
        return None
    graph = build_graph(knowledge_base)
    graph.metadata.setdefault("source", f"redis:{key}")
    if not quiet:
        print("KnowledgeBase loaded from Redis.")
        _print_counts(graph)
    return _Loaded(graph=graph, knowledge_base=knowledge_base, label=f"redis:{key}")


def _save_to_redis(loaded: _Loaded, key: str, *, quiet: bool) -> bool:
    try:
        store = RedisStore()
        graph_key = store.save_graph(loaded.graph, key)
        kb_key = (
            store.save_knowledge_base(loaded.knowledge_base, key)
            if loaded.knowledge_base is not None
            else None
        )
    except PersistenceError as error:
        print(f"error: {error}", file=sys.stderr)
        return False
    except Exception as error:
        print(f"error: cannot write '{key}' to Redis: {error}", file=sys.stderr)
        return False
    if not quiet:
        print(f"Saved graph to Redis: {graph_key}")
        if kb_key:
            print(f"Saved KnowledgeBase to Redis: {kb_key}")
    return True


# ----------------------------------------------------------------------
# File inputs
# ----------------------------------------------------------------------
def _load_lw_graph(raw_path: str, *, quiet: bool) -> Optional[_Loaded]:
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
    return _Loaded(graph=graph, label=str(source))


def _load_knowledge_graph(raw_path: str, *, quiet: bool) -> Optional[_Loaded]:
    path = Path(raw_path)
    if not quiet:
        print(f"Loading {path}...")
    data = _read_json(path)
    if data is None:
        return None
    if not any(key in data for key in ("entities", "concepts", "facts", "relations")):
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
    return _Loaded(graph=graph, knowledge_base=knowledge_base, label=str(path))


def _load_saved_graph(raw_path: str, *, quiet: bool) -> Optional[_Loaded]:
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
    return _Loaded(graph=graph, label=str(path))


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
