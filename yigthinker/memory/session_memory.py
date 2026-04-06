from __future__ import annotations
import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yigthinker.providers.base import LLMProvider

from yigthinker.types import Message

MEMORY_TEMPLATE = """\
# Data Source Knowledge
_Table structures, field semantics, data quality issues, join relationships discovered during analysis._

# Business Rules & Patterns
_Financial cycles, seasonal patterns, customer behaviors, industry norms. No specific amounts or customer PII._

# Errors & Corrections
_Failed SQL queries, incorrect analysis approaches, and their fixes. What NOT to try again._

# Key Findings
_Important analytical conclusions from this project. Referenced by finding ID for traceability._

# Analysis Log
_Terse step-by-step record of analysis sessions. One line per significant action._
"""

EXTRACTION_PROMPT = """\
Analyze the following conversation turns and extract any new knowledge into the categories below.
Return ONLY new findings. Do not repeat information already in the existing memory.
If there are no new findings for a category, omit that category entirely.
Return plain Markdown with section headers matching the categories.

Categories:
- Data Source Knowledge: table structures, field semantics, data quality issues, join relationships
- Business Rules & Patterns: financial cycles, seasonal patterns, customer behaviors
- Errors & Corrections: failed approaches and their fixes
- Key Findings: important analytical conclusions
- Analysis Log: one-line record of significant actions taken

Existing memory (for deduplication):
{existing_memory}

Recent conversation:
{recent_turns}

New findings only:
"""


class MemoryManager:
    def __init__(
        self,
        extract_frequency: int = 5,
        project_dir: Path | None = None,
    ) -> None:
        self._freq = extract_frequency
        self._project_dir = project_dir or Path.cwd()
        self._turn_count = 0
        self._extraction_running = False

    def record_turn(self) -> None:
        """Call after each assistant turn."""
        self._turn_count += 1

    def should_extract(self) -> bool:
        """True if extraction should run now."""
        if self._extraction_running:
            return False
        return self._turn_count > 0 and (self._turn_count % self._freq) == 0

    def memory_path(self) -> Path:
        """Path to MEMORY.md for the current project."""
        project_hash = hashlib.sha256(str(self._project_dir.resolve()).encode()).hexdigest()[:8]
        return self._project_dir / ".yigthinker" / "projects" / project_hash / "memory" / "MEMORY.md"

    def global_memory_path(self) -> Path:
        return Path.home() / ".yigthinker" / "memory" / "MEMORY.md"

    def ensure_memory_file(self) -> Path:
        """Create MEMORY.md with template if it doesn't exist."""
        path = self.memory_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(MEMORY_TEMPLATE, encoding="utf-8")
        return path

    def is_template_only(self, path: Path) -> bool:
        """Return True if MEMORY.md contains only template headers (no real content)."""
        if not path.exists():
            return True
        real_lines = [
            line for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
            and not line.startswith("#")
            and not (line.strip().startswith("_") and line.strip().endswith("_"))
        ]
        return len(real_lines) == 0

    def start_extraction(self) -> None:
        """Mark extraction as in-progress."""
        self._extraction_running = True

    def finish_extraction(self) -> None:
        """Mark extraction as complete."""
        self._extraction_running = False

    def load_memory(self) -> str:
        """Load project + global memory for context injection."""
        parts = []
        global_path = self.global_memory_path()
        if global_path.exists() and not self.is_template_only(global_path):
            parts.append("## Global Memory\n" + global_path.read_text(encoding="utf-8"))
        project_path = self.memory_path()
        if project_path.exists() and not self.is_template_only(project_path):
            parts.append("## Project Memory\n" + project_path.read_text(encoding="utf-8"))
        return "\n\n".join(parts)

    async def extract_memories(
        self, messages: list[Message], provider: LLMProvider,
    ) -> str | None:
        """Send recent turns to LLM and append extracted findings to MEMORY.md."""
        self.start_extraction()
        try:
            # Take last freq*2 messages (approx N turns = 2N messages)
            window = self._freq * 2
            recent = messages[-window:]
            formatted_turns = "\n".join(
                f"{m.role}: {m.content if isinstance(m.content, str) else str(m.content)}"
                for m in recent
            )
            existing = self.load_memory()
            prompt = EXTRACTION_PROMPT.format(
                existing_memory=existing or "(empty)",
                recent_turns=formatted_turns,
            )
            response = await provider.chat(
                [Message(role="user", content=prompt)], tools=[],
            )
            text = response.text.strip() if response.text else ""
            if text:
                self._append_to_memory(text)
                return text
            return None
        finally:
            self.finish_extraction()

    def _append_to_memory(self, new_findings: str) -> None:
        """Append new findings into the appropriate sections of MEMORY.md."""
        path = self.ensure_memory_file()
        existing = path.read_text(encoding="utf-8")
        new_sections = self._parse_sections(new_findings)
        for header, content in new_sections.items():
            if not content.strip():
                continue
            existing = self._insert_after_header(existing, header, content)
        path.write_text(existing, encoding="utf-8")

    def _parse_sections(self, text: str) -> dict[str, str]:
        """Split markdown text by H1 headers. Returns {header: content}."""
        sections: dict[str, str] = {}
        current_header = ""
        current_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("# "):
                if current_header and current_lines:
                    sections[current_header] = "\n".join(current_lines)
                current_header = line[2:].strip()
                current_lines = []
            elif current_header:
                current_lines.append(line)
        if current_header and current_lines:
            sections[current_header] = "\n".join(current_lines)
        return sections

    def _insert_after_header(self, existing: str, header: str, new_content: str) -> str:
        """Insert new_content into the existing text under the matching header section."""
        lines = existing.splitlines(keepends=True)
        result: list[str] = []
        inserted = False
        i = 0
        while i < len(lines):
            line = lines[i]
            result.append(line)
            # Check if this line is the target header
            if not inserted and line.strip() == f"# {header}":
                # Skip past the italic description line if present
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    result.append(next_line)
                    # If next line is another header, insert before it
                    if next_line.strip().startswith("# ") and i > 0:
                        # Remove the header we just added, insert content, re-add header
                        result.pop()
                        content_with_newline = new_content.rstrip("\n") + "\n"
                        result.append(content_with_newline)
                        result.append(next_line)
                        inserted = True
                        break
                    i += 1
                else:
                    # Reached end of file; insert content here
                    content_with_newline = new_content.rstrip("\n") + "\n"
                    result.append(content_with_newline)
                    inserted = True
                    continue
            i += 1
        if not inserted:
            # Header not found; append as new section
            result.append(f"\n# {header}\n{new_content.rstrip(chr(10))}\n")
        return "".join(result)
