"""Text decoding for source files (UTF-8, GBK, Big5, ...).

Chinese source files are frequently encoded as GBK/GB18030 instead of UTF-8,
so plain ``read_text()`` is not enough. The strategy is deliberately small and
deterministic:

1. an explicitly requested encoding, if the caller knows it;
2. a byte order mark, which is authoritative;
3. strict UTF-8 (the common case);
4. ``charset_normalizer`` (same detector family used by ``requests``);
5. strict GB18030 (a superset of GBK) and then Big5;
6. last resort: UTF-8 with replacement characters, flagged as lossy.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from typing import Optional, Tuple

try:  # optional: only used to improve detection for legacy encodings
    from charset_normalizer import from_bytes as _detect_from_bytes
except ImportError:  # pragma: no cover - exercised only without the library
    _detect_from_bytes = None

#: Tried in order when no BOM is present.
FALLBACK_ENCODINGS: Tuple[str, ...] = ("utf-8", "gb18030", "big5")

#: Byte order marks, longest first so UTF-32 is not mistaken for UTF-16.
BOM_ENCODINGS: Tuple[Tuple[bytes, str], ...] = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


@dataclass(frozen=True)
class DecodedText:
    """Decoded text plus the encoding that produced it."""

    text: str
    encoding: str
    had_errors: bool = False


def normalize_newlines(text: str) -> str:
    """Normalize CRLF / CR to LF so all parsers produce identical line breaks."""

    return text.replace("\r\n", "\n").replace("\r", "\n")


def decode_bytes(data: bytes, encoding: Optional[str] = None) -> DecodedText:
    """Decode ``data`` into text, never raising on unknown encodings.

    Args:
        data: Raw file bytes (normally including any BOM).
        encoding: Optional explicit encoding; when given it is used as-is.

    Returns:
        The decoded text together with the encoding that was used and whether
        characters had to be replaced.
    """

    if encoding is not None:
        return DecodedText(normalize_newlines(data.decode(encoding)), encoding)

    for bom, codec in BOM_ENCODINGS:
        if data.startswith(bom):
            return DecodedText(normalize_newlines(data.decode(codec)), codec)

    try:
        return DecodedText(normalize_newlines(data.decode("utf-8")), "utf-8")
    except UnicodeDecodeError:
        pass

    detected = _detect_encoding(data)
    if detected is not None:
        try:
            return DecodedText(normalize_newlines(data.decode(detected)), detected)
        except (UnicodeDecodeError, LookupError):
            pass

    for codec in FALLBACK_ENCODINGS[1:]:
        try:
            return DecodedText(normalize_newlines(data.decode(codec)), codec)
        except UnicodeDecodeError:
            continue

    return DecodedText(
        normalize_newlines(data.decode("utf-8", errors="replace")),
        "utf-8",
        had_errors=True,
    )


def _detect_encoding(data: bytes) -> Optional[str]:
    """Best guess from ``charset_normalizer``, or ``None`` when unavailable."""

    if _detect_from_bytes is None or not data:
        return None
    match = _detect_from_bytes(data).best()
    return getattr(match, "encoding", None) if match is not None else None
