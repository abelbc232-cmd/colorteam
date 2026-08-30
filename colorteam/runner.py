"""Runs an agent against a document.

Two modes:
  --dry-run   assemble and print the exact prompt, no API call, no key needed.
              This is how you review what an agent will actually ask.
  live        call the Anthropic API and write the result to runs/.

Every run is written to runs/<timestamp>-<agent>.md so outputs are auditable
and diffable between drafts. Nothing is overwritten.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .registry import Agent

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env() -> None:
    """Load .env from the repo root if python-dotenv is installed.

    Falls back to a minimal parser so the CLI still works from a bare checkout
    with no dependencies beyond PyYAML.
    """
    if not ENV_PATH.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH, override=False)
        return
    except ImportError:
        pass
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env()

DEFAULT_MODEL = os.environ.get("COLORTEAM_MODEL", "claude-sonnet-4-5")


class MissingAPIKey(RuntimeError):
    pass


def assemble(agent: Agent, document: str, extra: dict[str, str] | None = None) -> dict:
    """Return the system prompt and user message without calling anything."""
    return {
        "system": agent.prompt,
        "user": agent.build_prompt(document, extra),
    }


def run(
    agent: Agent,
    document: str,
    extra: dict[str, str] | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 8000,
) -> str:
    """Call the model and return the text output."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise MissingAPIKey(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env, or use --dry-run."
        )

    from anthropic import Anthropic  # imported here so --dry-run needs no SDK

    client = Anthropic(api_key=api_key)
    payload = assemble(agent, document, extra)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=payload["system"],
        messages=[{"role": "user", "content": payload["user"]}],
    )
    return "".join(block.text for block in message.content if block.type == "text")


def save_run(agent: Agent, output: str, source: str) -> Path:
    RUNS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RUNS_DIR / f"{stamp}-{agent.name.lower()}.md"
    header = (
        f"<!-- agent: {agent.name} | stage: {agent.stage} | "
        f"source: {source} | generated: {stamp} -->\n\n"
    )
    path.write_text(header + output, encoding="utf-8")
    return path
