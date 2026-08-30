"""Reading proposal text out of the formats proposals actually arrive in.

Federal proposals live in Word, not Markdown. A tool that only reads .md is a
demo; one that reads .docx is usable on a Tuesday afternoon with a real draft.

Everything downstream (lint, the agents) works on plain text with line numbers,
so a loader's only job is to produce that text in a stable, reproducible order.
"""

from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".text"}
DOCX_SUFFIXES = {".docx"}
SUPPORTED = TEXT_SUFFIXES | DOCX_SUFFIXES


class UnsupportedDocument(ValueError):
    pass


class MissingDependency(RuntimeError):
    pass


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_docx(path: Path) -> str:
    """Extract paragraphs and table cells in document order.

    Word stores tables outside the paragraph stream, so a naive paragraph walk
    silently drops every compliance table in the document — which in a proposal
    is usually where the requirements live. This walks the body XML instead, so
    the output order matches what a human reads on the page.
    """
    try:
        from docx import Document  # python-docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:  # pragma: no cover - exercised by hand
        raise MissingDependency(
            "Reading .docx needs python-docx. Install it with: "
            "pip install python-docx"
        ) from exc

    document = Document(str(path))
    body = document.element.body
    lines: list[str] = []

    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            text = Paragraph(child, document).text.strip()
            lines.append(text)
        elif tag == "tbl":
            for row in Table(child, document).rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                lines.append(" | ".join(cells))

    # Collapse runs of blank lines so line numbers stay meaningful to a reader.
    cleaned: list[str] = []
    for line in lines:
        if line or (cleaned and cleaned[-1]):
            cleaned.append(line)
    return "\n".join(cleaned).strip() + "\n"


def load_document(path: str | Path) -> str:
    """Return the plain text of a document, chosen by file extension."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no such file: {path}")

    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return _load_text(path)
    if suffix in DOCX_SUFFIXES:
        return _load_docx(path)

    raise UnsupportedDocument(
        f"cannot read {suffix or 'a file with no extension'}. "
        f"Supported: {', '.join(sorted(SUPPORTED))}"
    )
