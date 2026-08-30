"""Tests for the compliance matrix and its spreadsheet round trip.

The round trip is the point: a human must be able to correct the extraction and
have the correction survive, be reported, and change what downstream checks
count. So these tests follow a correction all the way through rather than
stopping at "the file parsed".
"""

import pytest

from colorteam import matrix

TABLE = """
Some prose the agent wrote before the table.

| ID | Source | Requirement | Type | Volume | Section | Eval criterion | Page limit | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L-001 | L.2, p.12 | The Technical Volume shall not exceed 25 pages. | submission | I |  |  | 25 | proposal mgr | open |
| L-003 | L.3, p.14 | The offeror shall describe its sustainment approach. | submission | I | 2.1 | M-001 |  | tech lead | open |
| M-001 | M.2, p.51 | The Government will evaluate the sustainment approach. | evaluation | I | 2.1 |  |  | capture | open |

Trailing prose.
"""


def test_parses_a_markdown_table():
    rows = matrix.from_markdown(TABLE)
    assert [r.id for r in rows] == ["L-001", "L-003", "M-001"]
    assert rows[1].section == "2.1"
    assert rows[1].eval_criterion == "M-001"


def test_ignores_prose_around_the_table():
    rows = matrix.from_markdown(TABLE)
    assert all(r.id.startswith(("L-", "M-")) for r in rows)


def test_maps_columns_by_name_not_position():
    reordered = """
| Requirement | ID | Section |
| --- | --- | --- |
| The offeror shall do the thing. | L-009 | 3.2 |
"""
    rows = matrix.from_markdown(reordered)
    assert rows[0].id == "L-009"
    assert rows[0].requirement == "The offeror shall do the thing."
    assert rows[0].section == "3.2"


def test_unknown_columns_do_not_shift_the_rest():
    with_extra = """
| ID | Confidence | Requirement |
| --- | --- | --- |
| L-010 | high | The offeror shall do the other thing. |
"""
    rows = matrix.from_markdown(with_extra)
    assert rows[0].id == "L-010"
    assert rows[0].requirement == "The offeror shall do the other thing."


def test_rows_without_an_id_or_text_are_dropped():
    rows = matrix.from_markdown("| ID | Requirement |\n| --- | --- |\n|  | orphan |\n")
    assert rows == []


def test_markdown_round_trips():
    rows = matrix.from_markdown(TABLE)
    assert [r.id for r in matrix.from_markdown(matrix.to_markdown(rows))] == \
           [r.id for r in rows]


def test_json_round_trips(tmp_path):
    rows = matrix.from_markdown(TABLE)
    path = matrix.save_json(rows, tmp_path / "m.json")
    assert [r.id for r in matrix.load_json(path)] == [r.id for r in rows]


def test_load_dispatches_on_extension(tmp_path):
    rows = matrix.from_markdown(TABLE)
    md = tmp_path / "m.md"; md.write_text(TABLE, encoding="utf-8")
    js = matrix.save_json(rows, tmp_path / "m.json")
    assert len(matrix.load(md)) == len(matrix.load(js)) == 3


# --- flags ----------------------------------------------------------------


def test_a_flagged_row_stops_counting_as_live():
    row = matrix.Requirement(id="L-1", requirement="x")
    assert row.live
    for flag in ("mis-extracted", "duplicate", "not-a-requirement"):
        row.flag = flag
        assert not row.live


def test_an_added_row_is_still_live():
    row = matrix.Requirement(id="L-1", requirement="x", flag="added")
    assert row.live


# --- the spreadsheet round trip -------------------------------------------


@pytest.fixture
def workbook(tmp_path):
    pytest.importorskip("openpyxl")
    rows = matrix.from_markdown(TABLE)
    return rows, matrix.export_workbook(rows, tmp_path / "matrix.xlsx")


def test_export_writes_a_workbook(workbook):
    _, path = workbook
    assert path.exists() and path.stat().st_size > 0


def test_export_includes_instructions(workbook):
    openpyxl = pytest.importorskip("openpyxl")
    _, path = workbook
    book = openpyxl.load_workbook(path)
    assert "How to use this" in book.sheetnames
    assert "Compliance matrix" in book.sheetnames


def test_import_reads_back_what_was_exported(workbook):
    rows, path = workbook
    back, report = matrix.import_workbook(path)
    assert [r.id for r in back] == [r.id for r in rows]
    assert report["total"] == 3
    assert report["live"] == 3


def test_a_human_correction_survives_the_round_trip(workbook):
    openpyxl = pytest.importorskip("openpyxl")
    rows, path = workbook

    book = openpyxl.load_workbook(path)
    sheet = book["Compliance matrix"]
    sheet.cell(row=3, column=6).value = "2.9"          # move L-003 to a new section
    sheet.cell(row=4, column=12).value = "mis-extracted"  # reject M-001
    sheet.cell(row=4, column=11).value = "This is an eval criterion, not an obligation"
    sheet.append(["L-099", "L.9, p.20", "The offeror shall provide a security plan.",
                  "submission", "I", "2.5", "M-005", "", "capture", "open", "", "added"])
    book.save(path)

    back, report = matrix.import_workbook(path)

    assert len(back) == 4
    assert report["live"] == 3
    assert report["added_by_hand"] == ["L-099"]
    assert report["rejected"][0]["id"] == "M-001"
    assert "eval criterion" in report["rejected"][0]["note"]
    assert next(r for r in back if r.id == "L-003").section == "2.9"


def test_diff_names_what_changed(workbook):
    openpyxl = pytest.importorskip("openpyxl")
    rows, path = workbook

    book = openpyxl.load_workbook(path)
    sheet = book["Compliance matrix"]
    sheet.cell(row=3, column=6).value = "2.9"
    sheet.append(["L-099", "", "New requirement.", "submission", "I", "2.5",
                  "", "", "", "open", "", "added"])
    book.save(path)

    back, _ = matrix.import_workbook(path)
    changes = matrix.diff(rows, back)

    assert changes["added"] == ["L-099"]
    assert changes["removed"] == []
    assert changes["edited"] == [{"id": "L-003", "fields": ["section"]}]


def test_diff_ignores_note_and_flag_columns(workbook):
    """A reviewer note is not a change to the requirement itself."""
    openpyxl = pytest.importorskip("openpyxl")
    rows, path = workbook
    book = openpyxl.load_workbook(path)
    sheet = book["Compliance matrix"]
    sheet.cell(row=2, column=11).value = "checked against the PDF"
    book.save(path)

    back, _ = matrix.import_workbook(path)
    assert matrix.diff(rows, back)["edited"] == []
