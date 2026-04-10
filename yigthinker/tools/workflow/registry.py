from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

# ---------------------------------------------------------------------------
# Phase 9 lazy-default fields (D-13)
# ---------------------------------------------------------------------------
# These defaults are filled into workflow entries and manifest version entries
# on READ only. The first Phase 9 write (via save_index / save_manifest) that
# supplies real values upgrades the on-disk state; until then, Phase 8 entries
# stay untouched on disk but look Phase-9-shaped to callers.
#
# DO NOT reference these from outside this module except in tests.
_PHASE9_WORKFLOW_DEFAULTS: dict = {
    "target": None,
    "deploy_mode": None,
    "schedule": None,
    "last_deployed": None,
    "last_run": None,
    "last_run_status": None,
    "failure_count_30d": 0,
    "run_count_30d": 0,
    "deploy_id": None,
    "current_version": None,  # None means "fallback to latest_version"
}

_PHASE9_VERSION_DEFAULTS: dict = {
    "deployed_to": None,
    "deploy_mode": None,
    "deploy_id": None,
    "status": "active",
}


def _fill_workflow_entry_defaults(entry: dict) -> dict:
    """Fill missing Phase 9 fields on a single registry workflow entry.

    Does NOT write back. Does NOT catch JSON errors. Pure in-memory dict fill.
    """
    for key, default in _PHASE9_WORKFLOW_DEFAULTS.items():
        entry.setdefault(key, default)
    return entry


def _fill_version_entry_defaults(version: dict) -> dict:
    """Fill missing Phase 9 fields on a manifest version entry."""
    for key, default in _PHASE9_VERSION_DEFAULTS.items():
        version.setdefault(key, default)
    return version


class WorkflowRegistry:
    """File-based versioned storage for generated workflows.

    Uses filelock + atomic os.replace for concurrent-safe writes.
    Storage layout: base_dir/{name}/manifest.json + v{n}/ directories.
    Global index at base_dir/registry.json tracks all workflows.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or Path.home() / ".yigthinker" / "workflows"
        self._index_path = self._base_dir / "registry.json"
        self._lock = FileLock(str(self._index_path) + ".lock", timeout=10)

    def _ensure_dirs(self) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def load_index(self) -> dict:
        """Load the global registry index. Returns empty structure if missing.

        Phase 9: fills Phase 9 default fields on every workflow entry via
        ``_fill_workflow_entry_defaults`` (lazy default on read, D-13).
        ``JSONDecodeError`` on a corrupted file PROPAGATES (Pitfall 5) —
        callers surface it as ``ToolResult(is_error=True)``.
        """
        if not self._index_path.exists():
            return {"workflows": {}, "suppressed_suggestions": []}
        data = json.loads(self._index_path.read_text(encoding="utf-8"))
        for entry in data.get("workflows", {}).values():
            _fill_workflow_entry_defaults(entry)
        return data

    def save_index(self, data: dict) -> None:
        """Atomically write registry index with filelock protection.

        Merges ``data["workflows"]`` into the on-disk index under the lock
        so concurrent callers never lose each other's writes.
        """
        self._ensure_dirs()
        fd = None
        tmp_path = None
        try:
            with self._lock:
                # Read current state inside the lock for safe merging
                current = (
                    json.loads(self._index_path.read_text(encoding="utf-8"))
                    if self._index_path.exists()
                    else {"workflows": {}, "suppressed_suggestions": []}
                )
                # Per-entry merge: patches preserve existing fields instead
                # of replacing the whole entry (Phase 9 write-through).
                for wf_name, wf_patch in data.get("workflows", {}).items():
                    existing = current["workflows"].get(wf_name, {})
                    existing.update(wf_patch)
                    current["workflows"][wf_name] = existing
                if "suppressed_suggestions" in data:
                    current["suppressed_suggestions"] = data["suppressed_suggestions"]
                fd, tmp_path = tempfile.mkstemp(
                    dir=str(self._base_dir), suffix=".tmp",
                )
                content = json.dumps(current, indent=2, ensure_ascii=False)
                os.write(fd, content.encode("utf-8"))
                os.close(fd)
                fd = None
                os.replace(tmp_path, str(self._index_path))
                tmp_path = None
        finally:
            if fd is not None:
                os.close(fd)
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def next_version(self, name: str) -> int:
        """Return the next version number for a workflow (1-based sequential)."""
        manifest = self.get_manifest(name)
        if manifest is None:
            return 1
        return len(manifest["versions"]) + 1

    def get_manifest(self, name: str) -> dict | None:
        """Read the per-workflow manifest. Returns None if workflow doesn't exist.

        Phase 9: fills Phase 9 default fields on every version entry (D-13).
        """
        manifest_path = self._base_dir / name / "manifest.json"
        if not manifest_path.exists():
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for version in manifest.get("versions", []):
            _fill_version_entry_defaults(version)
        return manifest

    def save_manifest(self, name: str, manifest: dict) -> None:
        """Atomically write a per-workflow manifest."""
        workflow_dir = self._base_dir / name
        workflow_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = workflow_dir / "manifest.json"
        fd = None
        tmp_path = None
        try:
            with self._lock:
                fd, tmp_path = tempfile.mkstemp(
                    dir=str(workflow_dir), suffix=".tmp",
                )
                content = json.dumps(manifest, indent=2, ensure_ascii=False)
                os.write(fd, content.encode("utf-8"))
                os.close(fd)
                fd = None
                os.replace(tmp_path, str(manifest_path))
                tmp_path = None
        finally:
            if fd is not None:
                os.close(fd)
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def create(self, name: str, description: str, version_data: dict) -> Path:
        """Create a new workflow version. Returns the version directory path."""
        self._ensure_dirs()
        now = datetime.now(timezone.utc).isoformat()
        version = self.next_version(name)
        version_dir = self._base_dir / name / f"v{version}"
        version_dir.mkdir(parents=True, exist_ok=True)

        # Write version files
        for filename, content in version_data.items():
            (version_dir / filename).write_text(content, encoding="utf-8")

        # Build version entry
        version_entry = {
            "version": version,
            "created_at": now,
            "description": description,
            "files": list(version_data.keys()),
        }

        # Update manifest
        manifest = self.get_manifest(name)
        if manifest is None:
            manifest = {"name": name, "versions": []}
        manifest["versions"].append(version_entry)
        self.save_manifest(name, manifest)

        # Update registry index
        index = self.load_index()
        if name not in index["workflows"]:
            index["workflows"][name] = {
                "status": "active",
                "latest_version": version,
                "description": description,
                "created_at": now,
                "updated_at": now,
            }
        else:
            index["workflows"][name]["latest_version"] = version
            index["workflows"][name]["description"] = description
            index["workflows"][name]["updated_at"] = now
        self.save_index(index)

        return version_dir

    def update(
        self,
        name: str,
        description: str,
        version_data: dict,
        changelog: str = "",
    ) -> Path:
        """Create a new version of an existing workflow. Previous versions untouched."""
        version_dir = self.create(name, description, version_data)

        # Append changelog entry
        if changelog:
            changelog_path = self._base_dir / name / "changelog.txt"
            manifest = self.get_manifest(name)
            version = manifest["versions"][-1]["version"] if manifest else 1
            entry = f"v{version} ({datetime.now(timezone.utc).isoformat()}): {changelog}\n"
            with open(changelog_path, "a", encoding="utf-8") as f:
                f.write(entry)

        return version_dir

    def list_workflows(self) -> list[dict]:
        """Return list of workflow entries from registry index, with name included."""
        index = self.load_index()
        result = []
        for name, entry in index["workflows"].items():
            item = dict(entry)
            item["name"] = name
            result.append(item)
        return result
