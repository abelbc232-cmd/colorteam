"""Tests for document loading.

The docx test builds its fixture in-process rather than committing a binary,
so the test explains what it expects instead of hiding it in a file nobody
opens.
"""

from pathlib import Path

import pytest

from colorteam import loaders

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_loads_markdown():
    text = loaders.load_document(EXAMPLES / "sample-draft.md")
    assert "Technical Approach" in text


def test_loads_plain_text(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("The contractor shall submit a report.\n", encoding="utf-8")
    assert "shall submit" in loaders.load_document(path)


def test_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "sheet.xlsx"
    path.write_bytes(b"not really a spreadsheet")
    with pytest.raises(loaders.UnsupportedDocument) as exc:
        loaders.load_document(path)
    assert ".docx" in str(exc.value)


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        loaders.load_document("no-such-document.md")


def test_reads_docx_paragraphs_and_tables(tmp_path):
    docx = pytest.importorskip("docx")

    path = tmp_path / "draft.docx"
    document = docx.Document()
    document.add_heading("2.1 Technical Approach", level=1)
    document.add_paragraph("Our team will ensure continuous availability.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "ID"
    table.cell(0, 1).text = "Requirement"
    table.cell(1, 0).text = "L-014"
    table.cell(1, 1).text = "The offeror shall describe its approach."
    document.add_paragraph("Transition is comprehensive.")
    document.save(str(path))

    text = loaders.load_document(path)

    # Paragraphs survive.
    assert "Technical Approach" in text
    assert "will ensure continuous availability" in text
    # Table content survives — this is the case a paragraph-only walk drops.
    assert "L-014" in text
    assert "The offeror shall describe its approach." in text
    # Document order is preserved: the table sits between the two paragraphs.
    assert text.index("ensure") < text.index("L-014") < text.index("comprehensive")


def test_docx_findings_match_the_same_text_in_markdown(tmp_path):
    """A .docx and a .md with identical prose must lint identically."""
    docx = pytest.importorskip("docx")
    from colorteam import lint

    prose = [
        "Our team will ensure availability.",
        "We offer a comprehensive solution.",
        "We will strive to reduce repair time.",
    ]

    md_path = tmp_path / "draft.md"
    md_path.write_text("\n".join(prose) + "\n", encoding="utf-8")

    docx_path = tmp_path / "draft.docx"
    document = docx.Document()
    for line in prose:
        document.add_paragraph(line)
    document.save(str(docx_path))

    md_terms = sorted(f.term.lower() for f in lint.lint(loaders.load_document(md_path)))
    docx_terms = sorted(f.term.lower() for f in lint.lint(loaders.load_document(docx_path)))
    assert md_terms == docx_terms
