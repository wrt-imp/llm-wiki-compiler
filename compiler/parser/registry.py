"""Extension based parser dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

from .base import BaseParser, PathLike
from .document import Document
from .errors import UnsupportedFormatError
from .markdown_parser import MarkdownParser
from .pdf_parser import PdfParser
from .txt_parser import TxtParser


class ParserRegistry:
    """Maps file extensions to parsers.

    Deliberately a plain in-memory lookup table: no entry points, no dynamic
    plugin loading. Registering a parser is one method call.
    """

    def __init__(self, parsers: Iterable[BaseParser] = ()) -> None:
        self._parsers: Dict[str, BaseParser] = {}
        for parser in parsers:
            self.register(parser)

    def register(self, parser: BaseParser) -> BaseParser:
        """Register ``parser`` for each of its extensions."""

        for extension in parser.extensions:
            self._parsers[extension.lower()] = parser
        return parser

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        """All registered extensions, sorted for stable error messages."""

        return tuple(sorted(self._parsers))

    def get_parser(self, path: PathLike) -> BaseParser:
        """Return the parser for ``path``'s extension.

        Raises:
            UnsupportedFormatError: when the extension has no parser.
        """

        suffix = Path(path).suffix.lower()
        try:
            return self._parsers[suffix]
        except KeyError:
            supported = ", ".join(self.supported_extensions) or "none"
            label = f"'{suffix}'" if suffix else "no file extension"
            raise UnsupportedFormatError(
                f"unsupported file format: {label} for source '{path}'. "
                f"Supported extensions: {supported}"
            ) from None

    def parse(self, path: PathLike) -> Document:
        """Parse ``path`` with the parser selected from its extension."""

        return self.get_parser(path).parse(path)

    def parse_all(self, paths: Iterable[PathLike]) -> List[Document]:
        """Parse several files in order."""

        return [self.parse(path) for path in paths]


def create_default_registry() -> ParserRegistry:
    """Build the registry with the parsers of the current stage."""

    return ParserRegistry([TxtParser(), MarkdownParser(), PdfParser()])


#: Registry used by :func:`parse_file`.
registry = create_default_registry()


def parse_file(path: PathLike) -> Document:
    """Parse one file with the default registry.

    This is the entry point the CLI and later stages should call.
    """

    return registry.parse(path)
