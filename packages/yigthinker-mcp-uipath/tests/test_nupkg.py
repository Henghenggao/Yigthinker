"""Structural unit tests for yigthinker_mcp_uipath.nupkg.build_nupkg.

Verifies CONTEXT.md D-18 + RESEARCH.md Finding 4 (operate.json correction
over D-16's project.json wording).
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from yigthinker_mcp_uipath.nupkg import build_nupkg


@pytest.fixture
def trivial_script(tmp_path: Path) -> Path:
    script = tmp_path / "Main.py"
    script.write_text("print('hello world')\n", encoding="utf-8")
    return script


def test_nupkg_has_required_files(trivial_script: Path):
    data = build_nupkg(trivial_script, workflow_name="test_flow", version="1.0.0")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
    assert "[Content_Types].xml" in names
    assert "_rels/.rels" in names
    assert "test_flow.nuspec" in names
    assert "content/Main.py" in names
    # Finding 4: operate.json, NOT project.json
    assert "content/operate.json" in names
    assert "content/entry-points.json" in names
    assert "content/project.json" not in names  # Pitfall 6 guard
    # Exactly one .psmdcp under the core-properties path
    psmdcp_files = [
        n for n in names
        if n.startswith("package/services/metadata/core-properties/")
    ]
    assert len(psmdcp_files) == 1
    assert psmdcp_files[0].endswith(".psmdcp")


def test_nuspec_contains_package_metadata(trivial_script: Path):
    data = build_nupkg(trivial_script, workflow_name="test_flow", version="1.2.3")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        nuspec_text = zf.read("test_flow.nuspec").decode("utf-8-sig")
    assert "<id>test_flow</id>" in nuspec_text
    assert "<version>1.2.3</version>" in nuspec_text


def test_main_py_content_preserved(trivial_script: Path):
    data = build_nupkg(trivial_script, workflow_name="test_flow", version="1.0.0")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        main_py = zf.read("content/Main.py").decode("utf-8")
    assert main_py == "print('hello world')\n"


def test_operate_json_targets_python_runtime(trivial_script: Path):
    data = build_nupkg(trivial_script, workflow_name="test_flow", version="1.0.0")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        operate = json.loads(zf.read("content/operate.json"))
    assert operate["targetFramework"] == "Portable"
    assert operate["targetRuntime"] == "python"
    assert operate["contentType"] == "Process"
    assert operate["main"] == "Main.py"
    assert operate["runtimeOptions"]["requiresUserInteraction"] is False
    assert operate["runtimeOptions"]["isAttended"] is False
    assert operate["$schema"] == "https://cloud.uipath.com/draft/2024-12/entry-point"


def test_entry_points_json_lists_main(trivial_script: Path):
    data = build_nupkg(trivial_script, workflow_name="test_flow", version="1.0.0")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = json.loads(zf.read("content/entry-points.json"))
    assert len(entries["entryPoints"]) == 1
    ep = entries["entryPoints"][0]
    assert ep["filePath"] == "Main.py"
    assert ep["type"] == "process"
    assert "uniqueId" in ep
    assert ep["input"]["type"] == "object"


def test_psmdcp_filename_is_16_hex_chars(trivial_script: Path):
    data = build_nupkg(trivial_script, workflow_name="test_flow", version="1.0.0")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
    psmdcp_files = [
        n for n in names
        if n.startswith("package/services/metadata/core-properties/")
    ]
    assert len(psmdcp_files) == 1
    # Filename portion: package/services/metadata/core-properties/<basename>
    basename = psmdcp_files[0].split("/")[-1]
    assert re.match(r"^[0-9a-f]{16}\.psmdcp$", basename), (
        f"psmdcp basename {basename!r} does not match 16-hex-char pattern"
    )


def test_pure_function_no_disk_write(tmp_path: Path):
    script = tmp_path / "Main.py"
    script.write_text("x = 1\n", encoding="utf-8")
    before = set(tmp_path.iterdir())
    result = build_nupkg(script, workflow_name="t", version="1.0.0")
    after = set(tmp_path.iterdir())
    assert isinstance(result, bytes)
    assert len(result) > 0
    # Pure function: tmp_path contents unchanged after the call.
    assert before == after
