"""Self-tests for the presence import-graph lint."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "check_presence_boundaries.py"


def _run(args: list[str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + (args or []),
        capture_output=True, text=True, cwd=cwd or SCRIPT.parents[1],
    )


def test_presence_tree_has_no_boundary_violations():
    """Regression gate: the real yigthinker/presence/ tree must be clean.

    A failing assertion here means a new import snuck past the boundary.
    If you hit this, either fix the import to go through yigthinker.core.*,
    or add the file to ALLOWLIST in scripts/check_presence_boundaries.py
    with a # TODO(presence-bleed) rationale (budget: 3 entries).
    """
    r = _run()
    assert r.returncode == 0, (
        f"Presence boundary violations detected (exit {r.returncode}):\n"
        f"{r.stderr or r.stdout}"
    )


def test_script_catches_synthetic_violation(tmp_path, monkeypatch):
    """Create a fake presence/ file that imports yigthinker.agent; expect exit 2."""
    # Build a tiny fake tree
    fake = tmp_path / "fake_presence" / "bad_surface.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("from yigthinker.agent import AgentLoop  # bad\n")

    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path / "fake_presence")],
        capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert "bad_surface.py" in r.stdout + r.stderr
    assert "yigthinker.agent" in r.stdout + r.stderr


def test_script_allows_legal_imports(tmp_path):
    """Legal imports: stdlib, third-party, core, same-package-level presence."""
    good = tmp_path / "fake_presence" / "ok.py"
    good.parent.mkdir(parents=True)
    good.write_text(
        "import asyncio\n"
        "from typing import Any\n"
        "from yigthinker.core.presence import ChannelAdapter\n"
    )
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path / "fake_presence")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
