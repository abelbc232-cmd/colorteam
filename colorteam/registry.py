"""Loads agent definitions from agents/*.md.

An agent here is a plain Markdown file with YAML frontmatter. That is a
deliberate choice: a proposal manager who does not write Python can read,
review, and edit an agent without touching the codebase, and every change is
a reviewable diff in git.

Frontmatter contract:
    name        short uppercase handle used on the CLI
    stage       where it sits in the pursuit lifecycle
    purpose     one line, shown by `colorteam list`
    inputs      list of input names the agent expects
    output      the shape the agent must return
    references  optional list of files under reference/ to attach as context
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"


@dataclass
class Agent:
    name: str
    stage: str
    purpose: str
    inputs: list[str]
    output: str
    prompt: str
    references: list[str] = field(default_factory=list)
    path: Path | None = None

    def reference_text(self) -> str:
        """Concatenate the reference files this agent declares."""
        chunks = []
        for ref in self.references:
            ref_path = REFERENCE_DIR / ref
            if not ref_path.exists():
                raise FileNotFoundError(f"{self.name}: missing reference {ref}")
            chunks.append(
                f"<reference name=\"{ref}\">\n{ref_path.read_text(encoding='utf-8')}\n</reference>"
            )
        return "\n\n".join(chunks)

    def build_prompt(self, document: str, extra: dict[str, str] | None = None) -> str:
        """Assemble the full user message: references, then the document."""
        parts = []
        references = self.reference_text()
        if references:
            parts.append(references)
        for key, value in (extra or {}).items():
            parts.append(f"<{key}>\n{value}\n</{key}>")
        parts.append(f"<document>\n{document}\n</document>")
        parts.append(f"Produce your output as: {self.output}")
        return "\n\n".join(parts)


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        raise ValueError("agent file must start with YAML frontmatter")
    _, fm, body = raw.split("---", 2)
    return yaml.safe_load(fm) or {}, body.strip()


def load_agent(path: Path) -> Agent:
    meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    missing = {"name", "stage", "purpose", "output"} - set(meta)
    if missing:
        raise ValueError(f"{path.name}: frontmatter missing {sorted(missing)}")
    return Agent(
        name=meta["name"],
        stage=meta["stage"],
        purpose=meta["purpose"],
        inputs=meta.get("inputs", []),
        output=meta["output"],
        references=meta.get("references", []),
        prompt=body,
        path=path,
    )


def load_all(directory: Path | str = AGENTS_DIR) -> dict[str, Agent]:
    agents: dict[str, Agent] = {}
    for path in sorted(Path(directory).glob("*.md")):
        agent = load_agent(path)
        if agent.name in agents:
            raise ValueError(f"duplicate agent name: {agent.name}")
        agents[agent.name] = agent
    return agents


def get(name: str) -> Agent:
    agents = load_all()
    key = name.upper()
    if key not in agents:
        raise KeyError(f"unknown agent {name!r}. Known: {', '.join(sorted(agents))}")
    return agents[key]
