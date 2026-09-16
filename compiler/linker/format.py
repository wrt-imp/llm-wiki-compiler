"""Link formatting: markdown links, relative paths, escaping.

Only one style is used per run. The default (``markdown``) writes real
relative links, which is the only way to *guarantee* that a target exists and
that the path is correct in every renderer::

    [解析器](解析器.md)
    [my page](my%20page.md)

``wiki`` style (``[[解析器]]``) is available for Obsidian-like tools, where the
renderer resolves the name itself; it cannot guarantee the target because a
page whose file name changed to avoid a collision is only reachable by path.
"""

from __future__ import annotations

import posixpath
import re
from typing import Dict

LINK_STYLE_MARKDOWN = "markdown"
LINK_STYLE_WIKI = "wiki"

LINK_STYLES = (LINK_STYLE_MARKDOWN, LINK_STYLE_WIKI)

#: Characters that would break a markdown link destination.
_UNSAFE_IN_TARGET: Dict[str, str] = {
    " ": "%20",
    "(": "%28",
    ")": "%29",
    "<": "%3C",
    ">": "%3E",
    "#": "%23",
    "?": "%3F",
    "%": "%25",
    "`": "%60",
    '"': "%22",
    "[": "%5B",
    "]": "%5D",
}

#: Characters that would break the link text itself.
_UNSAFE_IN_DISPLAY = {"\\": "\\\\", "[": "\\[", "]": "\\]"}

_MULTI_SLASH_RE = re.compile(r"/{2,}")


def encode_target(path: str) -> str:
    """Percent-encode only what breaks a destination, keeping unicode readable."""

    return "".join(_UNSAFE_IN_TARGET.get(char, char) for char in path)


def escape_display(text: str) -> str:
    """Escape the characters that would break the surrounding link syntax."""

    return "".join(_UNSAFE_IN_DISPLAY.get(char, char) for char in text)


def relative_target(from_path: str, to_path: str) -> str:
    """POSIX relative path from one wiki file to another.

    Always uses ``/`` so the markdown is identical on Windows and POSIX, and
    never emits a drive letter or a backslash.
    """

    from_dir = posixpath.dirname(from_path.replace("\\", "/"))
    target = to_path.replace("\\", "/")
    if not from_dir:
        relative = target
    else:
        relative = posixpath.relpath(posixpath.normpath(target), from_dir)
    relative = _MULTI_SLASH_RE.sub("/", relative)
    if relative.startswith("./"):
        relative = relative[2:]
    return relative or posixpath.basename(target)


def format_link(
    display: str,
    target_path: str,
    *,
    from_path: str = "",
    style: str = LINK_STYLE_MARKDOWN,
) -> str:
    """Render one internal link.

    Args:
        display: The text as it appears in the page; never rewritten.
        target_path: The target page path from ``WikiPage``.
        from_path: Path of the page the link is written into, used to compute
            the relative target. Empty means "same directory".
        style: ``markdown`` (default) or ``wiki``.
    """

    if style == LINK_STYLE_WIKI:
        return f"[[{escape_display(display)}]]"
    if style not in LINK_STYLES:
        raise ValueError(
            f"unknown link style {style!r}; expected one of {', '.join(LINK_STYLES)}"
        )
    target = relative_target(from_path, target_path) if from_path else target_path
    return f"[{escape_display(display)}]({encode_target(target)})"
