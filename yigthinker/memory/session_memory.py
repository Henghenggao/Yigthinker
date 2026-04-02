from __future__ import annotations
import hashlib
from pathlib import Path

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
