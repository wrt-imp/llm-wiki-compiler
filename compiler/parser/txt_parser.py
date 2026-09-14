"""Plain text parser."""

from __future__ import annotations

from typing import Any, Dict

from .base import BaseParser, PathLike, first_non_empty_line
from .document import FORMAT_TXT, Document


class TxtParser(BaseParser):
    """TXT -> Document.

    The file is decoded with :func:`compiler.parser.encoding.decode_bytes`, so
    UTF-8, UTF-8 with BOM, GBK/GB18030 and Big5 files all work. The encoding
    that was used is reported in ``metadata["encoding"]``.
    """

    format = FORMAT_TXT
    extensions = (".txt",)

    def parse(self, path: PathLike) -> Document:
        source = self._resolve_source(path)
        decoded = self._read_text(source)
        content = decoded.text

        title = first_non_empty_line(content)
        metadata: Dict[str, Any] = {
            "encoding": decoded.encoding,
            "had_decoding_errors": decoded.had_errors,
            "line_count": len(content.splitlines()),
            "char_count": len(content),
        }
        return self._build_document(
            source, title=title, content=content, metadata=metadata
        )
