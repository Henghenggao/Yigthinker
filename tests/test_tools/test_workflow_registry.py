"""Tests for WorkflowRegistry: versioned workflow storage with concurrent-safe file I/O."""

from __future__ import annotations

import json
import concurrent.futures
from pathlib import Path

import pytest

from yigthinker.tools.workflow.registry import WorkflowRegistry


@pytest.fixture
def registry(tmp_path: Path) -> WorkflowRegistry:
    """Create a WorkflowRegistry backed by a temporary directory."""
    return WorkflowRegistry(base_dir=tmp_path)


def test_create_workflow(registry: WorkflowRegistry, tmp_path: Path) -> None:
    """create() builds v1/ directory, writes files, updates manifest and registry index."""
    version_dir = registry.create(
        name="monthly_report",
        description="Monthly AR aging report",
        version_data={"main.py": "print('hello')", "config.yaml": "db: sqlite"},
    )

    assert version_dir == tmp_path / "monthly_report" / "v1"
    assert version_dir.is_dir()
    assert (version_dir / "main.py").read_text(encoding="utf-8") == "print('hello')"
    assert (version_dir / "config.yaml").read_text(encoding="utf-8") == "db: sqlite"

    # Registry index updated
    index = registry.load_index()
    assert "monthly_report" in index["workflows"]
    entry = index["workflows"]["monthly_report"]
    assert entry["status"] == "active"
    assert entry["latest_version"] == 1

    # Manifest written
    manifest = registry.get_manifest("monthly_report")
    assert manifest is not None
    assert manifest["name"] == "monthly_report"
    assert len(manifest["versions"]) == 1
    assert manifest["versions"][0]["version"] == 1
    assert set(manifest["versions"][0]["files"]) == {"main.py", "config.yaml"}


def test_index_and_manifest(registry: WorkflowRegistry, tmp_path: Path) -> None:
    """registry.json and manifest.json follow the expected schema."""
    registry.create(
        name="budget_variance",
        description="Budget variance check",
        version_data={"main.py": "pass"},
    )

    # Index structure
    index_data = json.loads(
        (tmp_path / "registry.json").read_text(encoding="utf-8")
    )
    assert "workflows" in index_data
    wf = index_data["workflows"]["budget_variance"]
    assert wf["status"] == "active"
    assert wf["latest_version"] == 1
    assert "created_at" in wf
    assert "description" in wf

    # Manifest structure
    manifest_data = json.loads(
        (tmp_path / "budget_variance" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest_data["name"] == "budget_variance"
    v = manifest_data["versions"][0]
    assert v["version"] == 1
    assert "created_at" in v
    assert "description" in v
    assert "files" in v


def test_next_version(registry: WorkflowRegistry) -> None:
    """next_version returns 1 for new names, increments after create."""
    assert registry.next_version("new_workflow") == 1

    registry.create(
        name="new_workflow",
        description="First version",
        version_data={"main.py": "v1"},
    )
    assert registry.next_version("new_workflow") == 2


def test_previous_version_preserved(
    registry: WorkflowRegistry, tmp_path: Path
) -> None:
    """update() creates v2 while leaving v1 directory and files unchanged."""
    registry.create(
        name="reconciliation",
        description="Bank reconciliation v1",
        version_data={"main.py": "# v1 code"},
    )

    v1_content = (tmp_path / "reconciliation" / "v1" / "main.py").read_text(
        encoding="utf-8"
    )

    registry.update(
        name="reconciliation",
        description="Bank reconciliation v2",
        version_data={"main.py": "# v2 code"},
        changelog="Updated processing logic",
    )

    # v1 is untouched
    assert (tmp_path / "reconciliation" / "v1" / "main.py").read_text(
        encoding="utf-8"
    ) == v1_content

    # v2 exists with new content
    v2_dir = tmp_path / "reconciliation" / "v2"
    assert v2_dir.is_dir()
    assert (v2_dir / "main.py").read_text(encoding="utf-8") == "# v2 code"

    # Manifest has both versions
    manifest = registry.get_manifest("reconciliation")
    assert manifest is not None
    assert len(manifest["versions"]) == 2
    assert manifest["versions"][0]["version"] == 1
    assert manifest["versions"][1]["version"] == 2


def test_concurrent_writes(tmp_path: Path) -> None:
    """10 concurrent save_index calls do not corrupt registry.json."""
    reg = WorkflowRegistry(base_dir=tmp_path)
    reg._ensure_dirs()

    def write_entry(i: int) -> None:
        index = reg.load_index()
        index["workflows"][f"wf_{i}"] = {
            "status": "active",
            "latest_version": 1,
            "description": f"Workflow {i}",
        }
        reg.save_index(index)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(write_entry, i) for i in range(10)]
        concurrent.futures.wait(futures)
        for f in futures:
            f.result()  # raise if any failed

    # Verify: at least no corruption (valid JSON, some entries present)
    final_index = reg.load_index()
    assert isinstance(final_index["workflows"], dict)
    # With locking, all 10 should be present. Without locking, some may be lost.
    # We assert all 10 to prove locking works.
    assert len(final_index["workflows"]) == 10
    for i in range(10):
        assert f"wf_{i}" in final_index["workflows"]


def test_atomic_write(registry: WorkflowRegistry, tmp_path: Path) -> None:
    """Atomic write ensures file is either old or new content, never partial."""
    # Write initial index
    initial_data = {"workflows": {"existing": {"status": "active"}}, "suppressed_suggestions": []}
    registry.save_index(initial_data)

    # Read it back
    loaded = registry.load_index()
    assert loaded["workflows"]["existing"]["status"] == "active"

    # Write update atomically
    updated_data = {"workflows": {"existing": {"status": "paused"}, "new_wf": {"status": "active"}}, "suppressed_suggestions": []}
    registry.save_index(updated_data)

    # Verify update applied completely (not partially)
    loaded2 = registry.load_index()
    assert loaded2["workflows"]["existing"]["status"] == "paused"
    assert "new_wf" in loaded2["workflows"]


def test_get_manifest(registry: WorkflowRegistry) -> None:
    """get_manifest returns None for missing, dict for existing."""
    assert registry.get_manifest("nonexistent") is None

    registry.create(
        name="test_wf",
        description="Test",
        version_data={"main.py": "pass"},
    )
    manifest = registry.get_manifest("test_wf")
    assert manifest is not None
    assert manifest["name"] == "test_wf"
    assert len(manifest["versions"]) == 1


def test_list_workflows(registry: WorkflowRegistry) -> None:
    """list_workflows returns list of workflow entries with name field."""
    assert registry.list_workflows() == []

    registry.create(
        name="wf_alpha",
        description="Alpha workflow",
        version_data={"main.py": "pass"},
    )
    registry.create(
        name="wf_beta",
        description="Beta workflow",
        version_data={"main.py": "pass"},
    )

    workflows = registry.list_workflows()
    assert len(workflows) == 2
    names = {w["name"] for w in workflows}
    assert names == {"wf_alpha", "wf_beta"}
    # Each entry has expected fields
    for wf in workflows:
        assert "status" in wf
        assert "latest_version" in wf
        assert "name" in wf
