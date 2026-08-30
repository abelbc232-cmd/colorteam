"""Turning specified figures into rendered ones.

The revision stage emits each figure as a fenced ```mermaid block under a
heading, with an action caption above it. This module pulls those blocks out of
a draft and produces two things: one `.mmd` file per figure, and a single HTML
page that renders all of them together.

Rendering happens in the browser, via Mermaid loaded from a CDN. That is a
deliberate choice over a local toolchain: no Node install, no headless browser,
no system dependency to explain to whoever clones this. The HTML page opens on
any machine and prints to PDF, which is how proposal graphics get reviewed
anyway. Where `mmdc` (mermaid-cli) does happen to be installed, `--svg` uses it
to write standalone files as well.

Captions are extracted with the figures because in a proposal the caption is the
argument. A figure whose caption reads "Figure 2-1: Maintenance Process" has
wasted the most-read line on the page, and this module surfaces that by putting
the caption where a reviewer has to look at it.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# "### Figure 2-1 — Sustainment cycle" or "## Figure 3: Architecture"
HEADING = re.compile(r"^#{2,4}\s*(Figure\s+[^\n]+)$", re.MULTILINE | re.IGNORECASE)
CAPTION = re.compile(
    r"\*\*Action caption:\*\*\s*(.+?)(?=\n\s*\n|\n```)", re.IGNORECASE | re.DOTALL
)
MERMAID = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)


@dataclass
class Figure:
    number: int
    title: str
    caption: str
    source: str

    @property
    def slug(self) -> str:
        text = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        return f"{self.number:02d}-{text}"[:60]

    @property
    def caption_is_a_label(self) -> bool:
        """A caption that names the figure instead of making a point.

        Short, no verb doing work, no benefit. Heuristic on purpose — it flags
        for a human rather than deciding.
        """
        if not self.caption:
            return True
        words = self.caption.split()
        return len(words) < 8


def extract(markdown: str) -> list[Figure]:
    """Find every specified figure in a draft, in document order."""
    figures: list[Figure] = []

    # Split on figure headings so each mermaid block is attributed to its heading.
    matches = list(HEADING.finditer(markdown))
    if not matches:
        # No headings: still recover bare mermaid blocks so nothing is lost.
        for index, block in enumerate(MERMAID.finditer(markdown), start=1):
            figures.append(
                Figure(index, f"Figure {index}", "", block.group(1).strip())
            )
        return figures

    for index, match in enumerate(matches, start=1):
        start = match.end()
        end = matches[index].start() if index < len(matches) else len(markdown)
        section = markdown[start:end]

        diagram = MERMAID.search(section)
        if not diagram:
            continue

        caption_match = CAPTION.search(section)
        caption = " ".join(caption_match.group(1).split()) if caption_match else ""

        figures.append(
            Figure(
                number=index,
                title=" ".join(match.group(1).split()),
                caption=caption,
                source=diagram.group(1).strip(),
            )
        )
    return figures


def write_sources(figures: list[Figure], out_dir: Path | str) -> list[Path]:
    """Write one .mmd file per figure."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for figure in figures:
        path = out_dir / f"{figure.slug}.mmd"
        path.write_text(figure.source + "\n", encoding="utf-8")
        written.append(path)
    return written


def render_svgs(figures: list[Figure], out_dir: Path | str) -> list[Path]:
    """Render to standalone SVG when mermaid-cli is available. Optional."""
    if not shutil.which("mmdc"):
        return []
    out_dir = Path(out_dir)
    rendered = []
    for figure in figures:
        source = out_dir / f"{figure.slug}.mmd"
        target = out_dir / f"{figure.slug}.svg"
        try:
            subprocess.run(
                ["mmdc", "-i", str(source), "-o", str(target), "-b", "transparent"],
                check=True, capture_output=True, timeout=60,
            )
            rendered.append(target)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    return rendered


def build_page(figures: list[Figure], title: str = "Proposal graphics") -> str:
    """One HTML page rendering every figure, with its caption and warnings."""
    blocks = []
    for figure in figures:
        warning = ""
        if figure.caption_is_a_label:
            warning = (
                '<p class="warn">This caption labels the figure rather than making '
                "an argument. Evaluators read captions first — say what the figure "
                "proves and why it benefits the customer.</p>"
            )
        caption = html.escape(figure.caption) or "<em>no action caption supplied</em>"
        blocks.append(
            f"""<figure>
  <h2>{html.escape(figure.title)}</h2>
  <pre class="mermaid">{html.escape(figure.source)}</pre>
  <figcaption>{caption}</figcaption>
  {warning}
</figure>"""
        )

    body = "\n".join(blocks) if blocks else "<p>No figures found in this draft.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font: 16px/1.6 Georgia, serif; max-width: 900px; margin: 0 auto;
         padding: 40px 24px 80px; background: #fbfbfa; color: #1a1d1a; }}
  h1 {{ font-family: system-ui, sans-serif; font-size: 28px; letter-spacing: -.02em; }}
  .meta {{ font-family: ui-monospace, monospace; font-size: 12px; color: #6b6f6b;
          margin-bottom: 40px; }}
  figure {{ margin: 0 0 56px; padding: 24px; background: #fff;
           border: 1px solid #e2e5e2; border-radius: 4px; }}
  h2 {{ font-family: system-ui, sans-serif; font-size: 17px; margin: 0 0 16px; }}
  figcaption {{ margin-top: 18px; padding-top: 14px; border-top: 1px solid #e2e5e2;
               font-size: 15px; }}
  .warn {{ margin: 12px 0 0; padding: 10px 14px; background: #fdf3ea;
          border-left: 3px solid #b4632a; font-size: 14px; color: #6b3c14; }}
  pre.mermaid {{ background: transparent; text-align: center; }}
  @media print {{ body {{ background: #fff; }} figure {{ break-inside: avoid;
                 border: none; padding: 0; }} }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="meta">{len(figures)} figure(s) · rendered from the draft's mermaid blocks · print to PDF for review</p>
{body}
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{ startOnLoad: true, theme: "neutral" }});</script>
</body>
</html>
"""
