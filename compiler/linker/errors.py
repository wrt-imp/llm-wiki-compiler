"""Errors raised by the Link Resolver stage."""

from __future__ import annotations


class LinkerError(Exception):
    """Base class for every link resolution failure."""


class LinkWriteError(LinkerError):
    """A resolved page could not be written.

    The message always contains the failing path and the operating system's
    reason.
    """


class DeadLinkError(LinkerError):
    """A generated link points at a page that does not exist."""
