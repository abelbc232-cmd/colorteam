"""The evidence base.

An agent that writes without evidence writes marketing. This module holds the
material a proposal is actually built from — capability statements, resumes,
past performance, prior proposals won and lost, pricing history — and packs the
relevant parts into a prompt with provenance attached, so a drafting agent can
cite where a claim came from and a reviewer can check it.

Two rules shape the design.

**Provenance travels with the text.** Every excerpt is wrapped in a tag naming
its source file and kind. A claim an agent cannot attribute to one of these
sources is a claim it must mark rather than assert.

**The material never leaves the machine.** `knowledge/` is gitignored. Real
capability statements, priced BOEs, and losing proposals are among the most
sensitive documents a company owns, and a portfolio repository is the last place
they belong. The repository ships the folder structure and synthetic examples;
the contents stay local.

Relevance ranking is deliberately plain term overlap rather than embeddings: no
extra dependency, no model call, no network, and a ranking a human can predict
and argue with. For a corpus of dozens-to-hundreds of documents it is enough.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .loaders import SUPPORTED, load_document

ROOT = Path(__file__).resolve().parent.parent / "knowledge"

# The kinds of evidence a proposal draws on. Each is a subdirectory.
KINDS = {
    "capabilities": "What the company does today — capability statements, tech descriptions.",
    "resumes": "Key personnel. Source for staffing and key-personnel sections.",
    "past-performance": "Prior contracts: scope, value, period, customer, outcomes.",
    "proposals-won": "Prior winning proposals. Reusable language and proven arguments.",
    "proposals-lost": "Prior losing proposals and their debriefs. Often more instructive.",
    "pricing": "Historical rates, BOEs, and pricing approaches. Never quoted directly into text.",
    "graphics": "Existing figures and their captions, for reuse or restyling.",
}

# Words too common in proposal prose to carry signal in a relevance score.
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "shall", "will", "from", "are",
    "our", "its", "their", "have", "has", "was", "were", "been", "not", "all",
    "any", "may", "can", "must", "each", "such", "into", "than", "then", "they",
    "which", "these", "those", "there", "where", "when", "what", "who", "how",
    "government", "offeror", "contractor", "proposal", "section", "page",
}

TOKEN = re.compile(r"[a-z0-9][a-z0-9\-']+")


@dataclass
class Source:
    path: Path
    kind: str
    text: str

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def words(self) -> int:
        return len(self.text.split())


def ensure_layout(root: Path | str = ROOT) -> Path:
    """Create the knowledge folders and their README if they do not exist."""
    root = Path(root)
    for kind, description in KINDS.items():
        (root / kind).mkdir(parents=True, exist_ok=True)
        readme = root / kind / "README.md"
        if not readme.exists():
            readme.write_text(
                f"# {kind}\n\n{description}\n\n"
                "Drop `.docx`, `.md`, or `.txt` files here. Nothing in this folder is\n"
                "committed — see the repository `.gitignore`.\n",
                encoding="utf-8",
            )
    return root


def tokens(text: str) -> set[str]:
    return {t for t in TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 2}


def load(kinds: list[str] | None = None, root: Path | str = ROOT) -> list[Source]:
    """Read every readable document in the requested kinds."""
    root = Path(root)
    if not root.exists():
        return []
    wanted = kinds or list(KINDS)
    sources: list[Source] = []
    for kind in wanted:
        folder = root / kind
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED:
                continue
            if path.name == "README.md":
                continue
            try:
                text = load_document(path)
            except Exception:
                continue  # an unreadable source must not break a drafting run
            if text.strip():
                sources.append(Source(path=path, kind=kind, text=text))
    return sources


def rank(sources: list[Source], query: str) -> list[tuple[Source, float]]:
    """Order sources by term overlap with the query, most relevant first.

    Scored as the share of query terms a source covers, so a long document does
    not outrank a short precise one simply by containing more words.
    """
    query_terms = tokens(query)
    if not query_terms:
        return [(s, 0.0) for s in sources]
    scored = []
    for source in sources:
        overlap = query_terms & tokens(source.text)
        scored.append((source, len(overlap) / len(query_terms)))
    scored.sort(key=lambda pair: (-pair[1], pair[0].name))
    return scored


def excerpt(source: Source, query: str, max_chars: int) -> str:
    """Return the most relevant window of a source, or all of it if it fits."""
    if len(source.text) <= max_chars:
        return source.text

    query_terms = tokens(query)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", source.text) if p.strip()]
    if not query_terms:
        return source.text[:max_chars]

    scored = sorted(
        paragraphs,
        key=lambda p: -len(query_terms & tokens(p)),
    )
    kept: list[str] = []
    budget = max_chars
    for paragraph in scored:
        if len(paragraph) + 2 > budget:
            continue
        kept.append(paragraph)
        budget -= len(paragraph) + 2
        if budget <= 0:
            break
    # Restore document order so the excerpt still reads as prose.
    kept_set = set(kept)
    ordered = [p for p in paragraphs if p in kept_set]
    return "\n\n".join(ordered) + "\n\n[…source truncated to the most relevant passages…]"


def pack(
    query: str = "",
    kinds: list[str] | None = None,
    max_chars: int = 60_000,
    per_source_chars: int = 12_000,
    root: Path | str = ROOT,
) -> str:
    """Assemble the knowledge block for a prompt, with provenance on each source.

    Returns an empty string when there is nothing to pack, so a caller can treat
    "no knowledge base" and "knowledge base not requested" identically.
    """
    sources = load(kinds=kinds, root=root)
    if not sources:
        return ""

    blocks: list[str] = []
    budget = max_chars
    for source, score in rank(sources, query):
        if budget <= 0:
            break
        body = excerpt(source, query, min(per_source_chars, budget))
        blocks.append(
            f'<source kind="{source.kind}" file="{source.name}" relevance="{score:.2f}">\n'
            f"{body}\n"
            f"</source>"
        )
        budget -= len(body)

    return (
        "The following are the ONLY sources you may draw facts from. Cite the "
        "file name when you use one. Anything not supported here must be marked, "
        "never asserted.\n\n" + "\n\n".join(blocks)
    )


def manifest(root: Path | str = ROOT) -> list[dict]:
    """A listing of what the knowledge base holds, for `knowledge list`."""
    return [
        {
            "kind": s.kind,
            "file": s.name,
            "words": s.words,
            "path": str(s.path),
        }
        for s in load(root=root)
    ]


def add(path: Path | str, kind: str, root: Path | str = ROOT) -> Path:
    """Copy a document into the knowledge base under the given kind."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}. Known: {', '.join(sorted(KINDS))}")
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"no such file: {source}")
    if source.suffix.lower() not in SUPPORTED:
        raise ValueError(
            f"cannot read {source.suffix or 'a file with no extension'}. "
            f"Supported: {', '.join(sorted(SUPPORTED))}"
        )
    destination = ensure_layout(root) / kind / source.name
    shutil.copy2(source, destination)
    return destination
