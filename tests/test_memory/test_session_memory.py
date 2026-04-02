import pytest
from pathlib import Path
from yigthinker.memory.session_memory import MemoryManager, MEMORY_TEMPLATE


def test_memory_template_has_sections():
    assert "Data Source Knowledge" in MEMORY_TEMPLATE
    assert "Business Rules" in MEMORY_TEMPLATE
    assert "Errors & Corrections" in MEMORY_TEMPLATE
    assert "Key Findings" in MEMORY_TEMPLATE
    assert "Analysis Log" in MEMORY_TEMPLATE


def test_should_extract_every_n_turns():
    mgr = MemoryManager(extract_frequency=5)
    # Should NOT extract at turns 1-4
    for _ in range(4):
        mgr.record_turn()
    assert not mgr.should_extract()
    # 5th turn should trigger
    mgr.record_turn()
    assert mgr.should_extract()


def test_should_not_extract_if_already_running():
    mgr = MemoryManager(extract_frequency=5)
    for _ in range(5):
        mgr.record_turn()
    mgr.start_extraction()
    assert not mgr.should_extract()


def test_memory_path_for_project(tmp_path):
    mgr = MemoryManager(project_dir=tmp_path)
    path = mgr.memory_path()
    assert ".yigthinker" in str(path)
    assert "MEMORY.md" in str(path)


def test_ensure_memory_file_creates_template(tmp_path):
    mgr = MemoryManager(project_dir=tmp_path)
    path = mgr.ensure_memory_file()
    assert path.exists()
    content = path.read_text()
    assert "Data Source Knowledge" in content


def test_is_template_only(tmp_path):
    mgr = MemoryManager(project_dir=tmp_path)
    path = mgr.ensure_memory_file()
    # Fresh file = template only, no actual content
    assert mgr.is_template_only(path)


def test_load_memory_empty_when_template_only(tmp_path):
    mgr = MemoryManager(project_dir=tmp_path)
    mgr.ensure_memory_file()
    # Template-only file should not contribute to loaded memory
    result = mgr.load_memory()
    assert result == ""


def test_load_memory_includes_real_content(tmp_path):
    mgr = MemoryManager(project_dir=tmp_path)
    path = mgr.ensure_memory_file()
    # Append real content
    path.write_text(
        "# Data Source Knowledge\norders table has 2M rows. Primary key is order_id.\n",
        encoding="utf-8"
    )
    result = mgr.load_memory()
    assert "orders table" in result
    assert "## Project Memory" in result
