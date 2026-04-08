from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AgentType:
    """A predefined agent type loaded from .yigthinker/agents/*.md (SPAWN-19)."""
    name: str
    description: str
    allowed_tools: list[str] | None
    model: str | None
    system_prompt: str


def load_agent_type(name: str, search_dirs: list[Path] | None = None) -> AgentType:
    """Load an agent type by name from .yigthinker/agents/ directory.

    Search order:
    1. .yigthinker/agents/{name}.md in current directory (project-level)
    2. ~/.yigthinker/agents/{name}.md (user-level)

    Raises FileNotFoundError if no matching agent type file is found.
    Raises ValueError if the file has invalid frontmatter.
    """
    if search_dirs is None:
        search_dirs = [
            Path.cwd() / ".yigthinker" / "agents",
            Path.home() / ".yigthinker" / "agents",
        ]

    for search_dir in search_dirs:
        path = search_dir / f"{name}.md"
        if path.exists():
            return _parse_agent_file(path)

    raise FileNotFoundError(
        f"Agent type '{name}' not found. Searched: "
        + ", ".join(str(d) for d in search_dirs)
    )


def _parse_agent_file(path: Path) -> AgentType:
    """Parse a .yigthinker/agents/*.md file with YAML frontmatter (D-10, D-11).

    Expected format:
    ---
    name: analyst
    description: Data analysis specialist
    allowed_tools:
      - sql_query
      - df_transform
    model: null
    ---

    System prompt body text here...
    """
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        raise ValueError(f"Agent type file must start with YAML frontmatter: {path}")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Invalid frontmatter in {path}: missing closing ---")

    front: dict[str, Any] = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()

    if "name" not in front:
        raise ValueError(f"Agent type file missing 'name' in frontmatter: {path}")

    return AgentType(
        name=front["name"],
        description=front.get("description", ""),
        allowed_tools=front.get("allowed_tools"),
        model=front.get("model"),
        system_prompt=body,
    )
