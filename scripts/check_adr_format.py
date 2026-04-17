"""ADR format validator for Yigthinker docs/adr/*.md.

Rules (per phase-1-design spec §2.2.1):
- Lang: en  -> <=500 words (whitespace-split, excluding code blocks)
- Lang: zh  -> <=750 CJK characters (len(text) excluding code blocks)
- No Lang header -> default zh
- Required sections: Context, Decision, Consequences, References
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

WORD_LIMIT = 500
CHAR_LIMIT = 750
REQUIRED_SECTIONS = ("Context", "Decision", "Consequences", "References")
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_LANG_LINE = re.compile(r"^Lang:\s*(en|zh)\s*$", re.MULTILINE | re.IGNORECASE)


@dataclass(frozen=True)
class AdrViolation:
    path: Path
    code: str
    message: str


def _strip_code_blocks(text: str) -> str:
    return _CODE_FENCE.sub("", text)


def _detect_lang(text: str) -> str:
    m = _LANG_LINE.search(text)
    return m.group(1).lower() if m else "zh"


def _count(text: str, lang: str) -> int:
    body = _strip_code_blocks(text)
    if lang == "en":
        return len(body.split())
    return len(body)


def _has_section(text: str, name: str) -> bool:
    return re.search(rf"^#{{1,6}}\s+{re.escape(name)}\s*$", text, re.MULTILINE) is not None


def check_file(path: Path) -> list[AdrViolation]:
    text = path.read_text(encoding="utf-8")
    violations: list[AdrViolation] = []
    lang = _detect_lang(text)
    count = _count(text, lang)
    if lang == "en" and count > WORD_LIMIT:
        violations.append(AdrViolation(path, "WORD_LIMIT", f"{count} words > {WORD_LIMIT}"))
    if lang == "zh" and count > CHAR_LIMIT:
        violations.append(AdrViolation(path, "CHAR_LIMIT", f"{count} chars > {CHAR_LIMIT}"))
    for section in REQUIRED_SECTIONS:
        if not _has_section(text, section):
            violations.append(AdrViolation(path, "MISSING_SECTION", f"missing '## {section}'"))
    return violations


def main(argv: list[str]) -> int:
    adr_dir = Path(argv[1]) if len(argv) > 1 else Path("docs/adr")
    files = sorted(p for p in adr_dir.glob("[0-9][0-9][0-9]-*.md"))
    if not files:
        print(f"no ADR files found under {adr_dir}", file=sys.stderr)
        return 1
    all_violations: list[AdrViolation] = []
    for p in files:
        all_violations.extend(check_file(p))
    for v in all_violations:
        print(f"{v.path}: [{v.code}] {v.message}", file=sys.stderr)
    return 2 if all_violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
