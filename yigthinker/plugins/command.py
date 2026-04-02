from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SlashCommand:
    name: str
    description: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    argument_hint: str = ""
    body: str = ""


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return {}, content

    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()

    return meta, match.group(2).strip()


def load_commands_from_dir(directory: Path) -> list[SlashCommand]:
    commands: list[SlashCommand] = []
    for md_file in sorted(directory.glob("*.md")):
        meta, body = _parse_frontmatter(md_file.read_text(encoding="utf-8"))
        commands.append(
            SlashCommand(
                name=md_file.stem,
                description=meta.get("description", ""),
                allowed_tools=[
                    item.strip()
                    for item in meta.get("allowed-tools", "").split(",")
                    if item.strip()
                ],
                argument_hint=meta.get("argument-hint", ""),
                body=body,
            )
        )
    return commands
