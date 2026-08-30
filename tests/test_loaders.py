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


# --- Word comments --------------------------------------------------------


def _docx_with_comments(path):
    """Build a .docx carrying two real Word comments.

    python-docx cannot write comments, so the parts are injected into the
    package directly — which is also how they are read back.
    """
    import shutil
    import zipfile

    docx = pytest.importorskip("docx")

    document = docx.Document()
    document.add_paragraph("Our team will ensure continuous availability.")
    document.add_paragraph("Transition completes within 45 days.")
    document.save(str(path))

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    comments_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="{W}">
  <w:comment w:id="1" w:author="Dana Reviewer" w:initials="DR" w:date="2026-08-30T10:00:00Z">
    <w:p><w:r><w:t>Cut the guarantee language here.</w:t></w:r></w:p>
  </w:comment>
  <w:comment w:id="2" w:author="Sam Capture" w:initials="SC" w:date="2026-08-30T11:00:00Z">
    <w:p><w:r><w:t>Add the transition graphic.</w:t></w:r></w:p>
  </w:comment>
</w:comments>"""

    temporary = path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(temporary, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                text = data.decode("utf-8")
                # Bracket the first paragraph's run with a comment range.
                text = text.replace(
                    "<w:p>", '<w:commentRangeStart w:id="1"/><w:p>', 1
                ).replace("</w:p>", '</w:p><w:commentRangeEnd w:id="1"/>', 1)
                data = text.encode("utf-8")
            elif item.filename == "[Content_Types].xml":
                text = data.decode("utf-8").replace(
                    "</Types>",
                    '<Override PartName="/word/comments.xml" ContentType='
                    '"application/vnd.openxmlformats-officedocument.'
                    'wordprocessingml.comments+xml"/></Types>',
                )
                data = text.encode("utf-8")
            target.writestr(item, data)
        target.writestr("word/comments.xml", comments_xml)
    shutil.move(str(temporary), str(path))
    return path


def test_extracts_word_comments(tmp_path):
    path = _docx_with_comments(tmp_path / "pink.docx")
    comments = loaders.extract_comments(path)

    assert len(comments) == 2
    assert comments[0]["author"] == "Dana Reviewer"
    assert comments[0]["text"] == "Cut the guarantee language here."
    assert comments[1]["author"] == "Sam Capture"


def test_comment_carries_the_text_it_marks(tmp_path):
    path = _docx_with_comments(tmp_path / "pink.docx")
    first = loaders.extract_comments(path)[0]
    assert "ensure continuous availability" in first["anchor"]


def test_a_docx_without_comments_returns_empty(tmp_path):
    docx = pytest.importorskip("docx")
    path = tmp_path / "clean.docx"
    document = docx.Document()
    document.add_paragraph("No comments here.")
    document.save(str(path))
    assert loaders.extract_comments(path) == []


def test_asking_a_markdown_file_for_comments_is_safe():
    assert loaders.extract_comments(EXAMPLES / "sample-draft.md") == []


def test_missing_file_returns_no_comments():
    assert loaders.extract_comments("nope.docx") == []


def test_format_comments_is_readable(tmp_path):
    path = _docx_with_comments(tmp_path / "pink.docx")
    rendered = loaders.format_comments(loaders.extract_comments(path))
    assert "Dana Reviewer" in rendered
    assert "says: Cut the guarantee language here." in rendered
    assert 'on: "' in rendered


def test_format_comments_empty():
    assert loaders.format_comments([]) == ""
