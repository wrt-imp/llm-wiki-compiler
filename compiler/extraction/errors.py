"""Errors raised by the extraction stage."""

from __future__ import annotations


class ExtractionError(Exception):
    """Base class for every extraction failure."""


class InvalidResponseError(ExtractionError):
    """The LLM answer could not be read as a JSON object."""


class InvalidPayloadError(ExtractionError):
    """The JSON was readable but does not satisfy the extraction contract."""
