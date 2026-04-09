from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock


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
        """Load the global registry index. Returns empty structure if missing."""
        if not self._index_path.exists():
            return {"workflows": {}, "suppressed_suggestions": []}
        return json.loads(self._index_path.read_text(encoding="utf-8"))

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
                current["workflows"].update(data.get("workflows", {}))
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
        """Read the per-workflow manifest. Returns None if workflow doesn't exist."""
        manifest_path = self._base_dir / name / "manifest.json"
        if not manifest_path.exists():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))

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
