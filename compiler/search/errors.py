"""Errors raised by the Search stage."""

from __future__ import annotations


class SearchError(Exception):
    """Base class for every search failure.

    Raised for example when the wiki directory does not exist; the message
    always contains the offending path.
    """
