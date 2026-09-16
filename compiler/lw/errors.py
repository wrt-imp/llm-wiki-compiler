"""Errors raised while reading and parsing ``.lw`` graph sources."""

from __future__ import annotations


class LWError(Exception):
    """Base class for every ``.lw`` failure."""


class LWFileError(LWError):
    """The ``.lw`` file could not be read (missing, not a file, unreadable)."""


class MermaidParseError(LWError):
    """The Mermaid source is not valid within the supported subset.

    Always carries a location, so the CLI can print ``file:line:column``
    instead of leaking an ``IndexError`` or ``KeyError``.
    """

    def __init__(
        self,
        message: str,
        *,
        line: int = 0,
        column: int = 0,
        source: str = "",
    ) -> None:
        self.message = message
        self.line = line
        self.column = column
        self.source = source
        super().__init__(str(self))

    @property
    def location(self) -> str:
        return f"{self.source or '<string>'}:{self.line}:{self.column}"

    def __str__(self) -> str:
        return (
            f"ParseError: {self.location}\n"
            f"Invalid Mermaid graph syntax: {self.message}"
        )
