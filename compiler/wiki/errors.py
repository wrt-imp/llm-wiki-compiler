"""Errors raised by the Wiki Generator stage."""

from __future__ import annotations


class WikiError(Exception):
    """Base class for every wiki generation failure."""


class WikiWriteError(WikiError):
    """A wiki page could not be written to disk.

    The message always contains the path that failed, plus the reason the
    operating system reported.
    """
