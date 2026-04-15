"""Tests for VarRegistry memory limit (Task 16)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from yigthinker.session import VarRegistry


def test_var_registry_enforces_memory_limit():
    reg = VarRegistry(max_bytes=1_000_000)  # 1MB limit
    # Create a DataFrame well over 1MB (1M float64 values ≈ 8MB)
    big_df = pd.DataFrame(np.random.randn(125_000, 1), columns=["x"])
    with pytest.raises(MemoryError, match="limit"):
        reg.set("big", big_df)
    assert "big" not in reg


def test_var_registry_allows_within_limit():
    reg = VarRegistry(max_bytes=10_000_000)
    small_df = pd.DataFrame({"a": [1, 2, 3]})
    reg.set("small", small_df)
    assert "small" in reg


def test_var_registry_replace_same_name_frees_old_bytes():
    """Replacing an existing variable should subtract its old size before
    checking the projected total — so replacing a big DF with a small DF must
    succeed even when the registry is near the limit.
    """
    reg = VarRegistry(max_bytes=2_000_000)  # 2MB
    # ~1.6MB
    big_df = pd.DataFrame(np.random.randn(200_000, 1), columns=["x"])
    reg.set("x", big_df)
    # Replacing with a tiny DataFrame must succeed (old size is subtracted)
    reg.set("x", pd.DataFrame({"a": [1]}))
    assert "x" in reg


def test_var_registry_non_dataframe_values_have_zero_tracked_size():
    """Chart JSON strings and other non-DataFrame values don't consume the
    tracked byte budget (they're cheap to hold).
    """
    reg = VarRegistry(max_bytes=1000)  # absurdly small limit
    # Long string — not a DataFrame, so not counted
    reg.set("chart", "x" * 100_000, var_type="chart")
    assert "chart" in reg


def test_var_registry_default_limit_is_2gb():
    reg = VarRegistry()
    assert reg._max_bytes == 2 * 1024 ** 3
