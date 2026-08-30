"""Tests for figure extraction and rendering."""

from pathlib import Path

from colorteam import graphics

DRAFT = """
## 2.1 Technical Approach

Prose about the approach.

### Figure 2-1 — Sustainment cycle

**Action caption:** Preventive maintenance on a 30-day cycle holds availability
above the required threshold, so the Government sees no degradation.

```mermaid
flowchart LR
  A[Inspection] --> B[Fault isolation]
  B --> C[Return to service]
```

More prose.

### Figure 2-2 — Transition timeline

**Action caption:** Maintenance Process

```mermaid
gantt
  title Transition
  section Phase 1
  Kickoff :a1, 2026-01-01, 14d
```
"""


def test_extracts_every_figure():
    figures = graphics.extract(DRAFT)
    assert len(figures) == 2
    assert figures[0].title.startswith("Figure 2-1")
    assert "flowchart LR" in figures[0].source


def test_extracts_the_action_caption():
    first = graphics.extract(DRAFT)[0]
    assert first.caption.startswith("Preventive maintenance on a 30-day cycle")
    assert "\n" not in first.caption  # normalized to one line


def test_flags_a_caption_that_is_only_a_label():
    figures = graphics.extract(DRAFT)
    assert figures[0].caption_is_a_label is False
    assert figures[1].caption_is_a_label is True   # "Maintenance Process"


def test_a_missing_caption_counts_as_a_label():
    figures = graphics.extract("### Figure 1 — X\n\n```mermaid\ngraph TD\nA-->B\n```\n")
    assert figures[0].caption == ""
    assert figures[0].caption_is_a_label is True


def test_bare_mermaid_blocks_are_still_recovered():
    figures = graphics.extract("```mermaid\ngraph TD\nA-->B\n```\n")
    assert len(figures) == 1
    assert figures[0].title == "Figure 1"


def test_no_figures_returns_empty():
    assert graphics.extract("Just prose, no diagrams.") == []


def test_slugs_are_filename_safe_and_ordered():
    figures = graphics.extract(DRAFT)
    slugs = [f.slug for f in figures]
    assert slugs[0].startswith("01-")
    assert slugs[1].startswith("02-")
    assert all(c.isalnum() or c == "-" for s in slugs for c in s)


def test_write_sources_writes_one_file_per_figure(tmp_path):
    figures = graphics.extract(DRAFT)
    written = graphics.write_sources(figures, tmp_path)
    assert len(written) == 2
    assert all(p.suffix == ".mmd" for p in written)
    assert "flowchart" in written[0].read_text(encoding="utf-8")


def test_page_renders_every_figure_and_escapes_content():
    page = graphics.build_page(graphics.extract(DRAFT))
    assert page.count('class="mermaid"') == 2
    assert "mermaid.min.js" in page
    assert "A[Inspection] --&gt; B[Fault isolation]" in page  # escaped, not raw


def test_page_warns_about_label_captions():
    page = graphics.build_page(graphics.extract(DRAFT))
    assert page.count("class=\"warn\"") == 1


def test_page_handles_an_empty_draft():
    page = graphics.build_page([])
    assert "No figures found" in page
