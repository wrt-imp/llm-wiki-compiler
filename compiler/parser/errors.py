"""Errors raised by the parser stage."""

from __future__ import annotations


class ParserError(Exception):
    """Base class for every parser failure."""


class UnsupportedFormatError(ParserError):
    """Raised when no parser is registered for a file extension."""


class SourceNotFoundError(ParserError):
    """Raised when the source path is missing or is not a regular file."""
