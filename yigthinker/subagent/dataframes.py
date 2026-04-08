from __future__ import annotations

from yigthinker.session import VarRegistry


def copy_dataframes_to_child(
    parent_vars: VarRegistry,
    child_vars: VarRegistry,
    dataframe_names: list[str],
) -> None:
    raise NotImplementedError


def merge_back_dataframes(
    parent_vars: VarRegistry,
    child_vars: VarRegistry,
    agent_name: str,
    original_names: set[str],
) -> str:
    raise NotImplementedError
