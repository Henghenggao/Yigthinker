from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from yigthinker.plugins.command import SlashCommand, load_commands_from_dir


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    author: str
    plugin_dir: Path


class PluginLoader:
    """Discovers Yigthinker plugins and loads their slash commands."""

    def __init__(self, plugin_dirs: list[Path] | None = None) -> None:
        self._dirs = plugin_dirs or [
            Path.home() / ".yigthinker" / "plugins",
            Path.cwd() / ".yigthinker" / "plugins",
        ]

    def discover(self) -> list[PluginManifest]:
        manifests: list[PluginManifest] = []
        for search_dir in self._dirs:
            if not search_dir.exists():
                continue
            for candidate in search_dir.iterdir():
                manifest_path = candidate / ".yigthinker-plugin" / "plugin.json"
                if not manifest_path.exists():
                    continue
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                manifests.append(
                    PluginManifest(
                        name=data.get("name", candidate.name),
                        version=data.get("version", "0.0.0"),
                        description=data.get("description", ""),
                        author=data.get("author", ""),
                        plugin_dir=candidate,
                    )
                )
        return manifests

    def load_commands(self) -> list[SlashCommand]:
        commands: list[SlashCommand] = []
        for manifest in self.discover():
            commands_dir = manifest.plugin_dir / "commands"
            if commands_dir.exists():
                commands.extend(load_commands_from_dir(commands_dir))
        return commands
