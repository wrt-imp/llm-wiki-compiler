"""Read ``.lw`` files (any encoding the parser stage understands)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..parser.encoding import (
    BOM_ENCODINGS,
    DecodedText,
    decode_bytes,
    normalize_newlines,
)
from .errors import LWFileError
from .model import MermaidDocument
from .parser import parse_mermaid


def load_lw_file(path: Any) -> MermaidDocument:
    """Read and parse one ``.lw`` file.

    The file is decoded with the same helper the document parser uses, so
    UTF-8, UTF-8 with BOM and GB18030 all work.

    Raises:
        LWFileError: when the path is missing, not a file or unreadable.
        MermaidParseError: when the Mermaid source leaves the supported subset.
    """

    source = Path(path)
    if not source.exists():
        raise LWFileError(f"graph source does not exist: '{source}'")
    if not source.is_file():
        raise LWFileError(f"graph source is not a file: '{source}'")
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise LWFileError(f"cannot read graph source '{source}': {exc}") from exc

    decoded = _decode_text(data)
    document = parse_mermaid(decoded.text, source=str(source))
    document.metadata["encoding"] = decoded.encoding
    document.metadata["had_decoding_errors"] = decoded.had_errors
    return document


def _decode_text(data: bytes) -> DecodedText:
    """Decode deterministically: BOM, UTF-8, GB18030, then the shared helper.

    ``.lw`` files are often short and mostly ASCII with a few Chinese labels, a
    shape where the statistical detector inside ``decode_bytes`` can guess
    wrong; trying GB18030 (a superset of GBK) first is both safer and
    predictable.
    """

    for bom, codec in BOM_ENCODINGS:
        if data.startswith(bom):
            return DecodedText(normalize_newlines(data.decode(codec)), codec)
    for codec in ("utf-8", "gb18030"):
        try:
            return DecodedText(normalize_newlines(data.decode(codec)), codec)
        except UnicodeDecodeError:
            continue
    return decode_bytes(data)
