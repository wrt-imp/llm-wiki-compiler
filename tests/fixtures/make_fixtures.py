"""Regenerate the committed PDF fixtures.

Run from the project root::

    python tests/fixtures/make_fixtures.py

This helper is the only place that needs ``fpdf2``; the test suite itself only
needs ``pypdf``.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

FIXTURES_DIR = Path(__file__).resolve().parent

#: CJK TrueType fonts fpdf2 can embed; the first existing one is used.
CJK_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
)


def find_cjk_font() -> Path:
    for candidate in CJK_FONT_CANDIDATES:
        font = Path(candidate)
        if font.is_file():
            return font
    raise SystemExit(
        "no CJK font found; add a path to CJK_FONT_CANDIDATES in this script"
    )


def build_sample_pdf() -> None:
    pdf = FPDF()
    pdf.set_title("Parser Design Notes")
    pdf.set_author("Wiki Compiler Team")
    pdf.set_font("helvetica", size=12)

    pdf.add_page()
    pdf.multi_cell(0, 8, "Page one: the parser stage turns sources into documents.")

    pdf.add_page()
    pdf.multi_cell(0, 8, "Page two: provenance marker P2 for later tracing.")

    pdf.output(str(FIXTURES_DIR / "sample.pdf"))


def build_chinese_pdf() -> None:
    pdf = FPDF()
    pdf.add_font("cjk", "", str(find_cjk_font()))
    pdf.set_font("cjk", size=14)

    pdf.add_page()
    pdf.multi_cell(0, 10, "知识图谱编译器：解析器阶段")

    pdf.add_page()
    pdf.multi_cell(0, 10, "第二页：保留页面信息，便于来源追踪。")

    pdf.output(str(FIXTURES_DIR / "chinese.pdf"))


def main() -> None:
    build_sample_pdf()
    build_chinese_pdf()
    print(f"wrote fixtures to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
