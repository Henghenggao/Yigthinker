from __future__ import annotations

import pandas as pd

from yigthinker.session import VarRegistry


def copy_dataframes_to_child(
    parent_vars: VarRegistry,
    child_vars: VarRegistry,
    dataframe_names: list[str],
) -> None:
    """Copy specified DataFrames from parent to child (SPAWN-04, D-02).

    - DataFrames are shallow-copied via pd.DataFrame.copy(deep=False).
      pandas 3.x Copy-on-Write makes this safe: mutations in child
      trigger a copy automatically.
    - Non-DataFrame values (charts, strings) are copied by reference.
    - Raises KeyError if a requested name does not exist in parent_vars.
    """
    for name in dataframe_names:
        value = parent_vars.get(name)  # raises KeyError if missing
        if isinstance(value, pd.DataFrame):
            child_vars.set(name, value.copy(deep=False))
        else:
            child_vars.set(name, value)


def merge_back_dataframes(
    parent_vars: VarRegistry,
    child_vars: VarRegistry,
    agent_name: str,
    original_names: set[str],
) -> str:
    """Merge child DataFrames back to parent with prefix (SPAWN-05, SPAWN-06, D-01, D-03).

    Every entry in child_vars is merged back with the ``{agent_name}_`` prefix.
    Returns a summary string for appending to tool_result text.

    ``original_names`` is currently unused but reserved for future diff-based
    merge strategies. All child vars are merged back regardless.
    """
    merged: list[str] = []
    for info in child_vars.list():
        prefixed_name = f"{agent_name}_{info.name}"
        value = child_vars.get(info.name)
        parent_vars.set(prefixed_name, value, var_type=info.var_type)
        if info.shape != (0, 0):
            merged.append(f"  {prefixed_name}: {info.shape[0]}x{info.shape[1]}")
        else:
            merged.append(f"  {prefixed_name}: ({info.var_type})")

    if merged:
        return "\n\nDataFrames merged back:\n" + "\n".join(merged)
    return ""
