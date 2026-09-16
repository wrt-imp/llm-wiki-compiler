"""The ``.lw`` graph source format: Mermaid in, project Graph out.

``.lw`` files are plain Mermaid graph sources - there is no invented syntax::

    graph TD
        Parser[解析器]
        DocumentModel[文档模型]
        Parser -->|produces| DocumentModel

The pipeline is::

    .lw -> Mermaid source -> parser -> parsed model -> adapter -> Graph

Only the graph subset of Mermaid is supported (see
:mod:`compiler.lw.parser`); anything else raises a located
:class:`~compiler.lw.errors.MermaidParseError`. The adapter reuses the existing
``compiler.graph`` model, so ``.lw`` graphs and knowledge graphs are the same
kind of object.
"""

from .adapter import (
    LW_ADAPTER_VERSION,
    LW_EDGE_KIND,
    LW_NODE_KIND,
    to_graph,
)
from .errors import LWError, LWFileError, MermaidParseError
from .loader import load_lw_file
from .model import MermaidDocument, MermaidEdge, MermaidNode
from .parser import DIRECTIONS, HEADER_KEYWORDS, PARSER_VERSION, parse_mermaid

__all__ = [
    "DIRECTIONS",
    "HEADER_KEYWORDS",
    "LWError",
    "LWFileError",
    "LW_ADAPTER_VERSION",
    "LW_EDGE_KIND",
    "LW_NODE_KIND",
    "MermaidDocument",
    "MermaidEdge",
    "MermaidNode",
    "MermaidParseError",
    "PARSER_VERSION",
    "load_lw_file",
    "parse_mermaid",
    "to_graph",
]
