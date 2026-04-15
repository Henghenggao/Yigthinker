import pandas as pd
import pytest
from yigthinker.session import SessionContext
from yigthinker.types import Message


def test_checkpoint_stores_state():
    ctx = SessionContext()
    ctx.messages.append(Message(role="user", content="hello"))
    ctx.vars.set("df1", pd.DataFrame({"a": [1, 2]}))

    ctx.checkpoint("step1")

    labels = ctx.list_checkpoints()
    assert "step1" in labels


def test_branch_from_restores_state():
    ctx = SessionContext()
    ctx.messages.append(Message(role="user", content="hello"))
    ctx.vars.set("df1", pd.DataFrame({"a": [1, 2]}))

    ctx.checkpoint("step1")

    # Modify parent after checkpoint
    ctx.messages.append(Message(role="assistant", content="hi"))
    ctx.vars.set("df2", pd.DataFrame({"b": [3]}))

    branched = ctx.branch_from("step1")

    # Branched should have state at checkpoint
    assert len(branched.messages) == 1
    assert branched.messages[0].content == "hello"
    assert "df1" in branched.vars
    assert "df2" not in branched.vars
    # Branched has a NEW session_id
    assert branched.session_id != ctx.session_id


def test_branch_from_unknown_raises():
    ctx = SessionContext()
    with pytest.raises(KeyError, match="nonexistent"):
        ctx.branch_from("nonexistent")


def test_branch_convenience():
    ctx = SessionContext()
    ctx.messages.append(Message(role="user", content="test"))
    ctx.vars.set("df1", pd.DataFrame({"x": [1]}))

    branched = ctx.branch()

    assert len(branched.messages) == 1
    assert "df1" in branched.vars
    assert branched.session_id != ctx.session_id
    # Internal temp label must be cleaned up
    assert not any(label.startswith("__branch__") for label in ctx.list_checkpoints())


def test_checkpoint_limit_evicts_oldest():
    ctx = SessionContext(settings={"session": {"max_checkpoints": 3}})

    for i in range(5):
        ctx.checkpoint(f"cp{i}")

    labels = ctx.list_checkpoints()
    assert len(labels) == 3
    assert "cp0" not in labels
    assert "cp1" not in labels
    assert "cp4" in labels


def test_branch_is_independent():
    ctx = SessionContext()
    ctx.vars.set("df1", pd.DataFrame({"a": [1]}))
    ctx.checkpoint("base")

    branched = ctx.branch_from("base")
    branched.vars.set("df_new", pd.DataFrame({"b": [2]}))

    assert "df_new" not in ctx.vars


def test_checkpoint_is_not_corrupted_by_mutation():
    """After checkpointing, mutating the original DataFrame must not affect the checkpoint."""
    ctx = SessionContext()
    df = pd.DataFrame({"x": [1, 2, 3]})
    ctx.vars.set("data", df)
    ctx.checkpoint("before_mutation")

    # Mutate the original DataFrame in-place
    df.iloc[0, 0] = 999

    # Restore from checkpoint
    restored = ctx.branch_from("before_mutation")
    restored_df = restored.vars.get("data")
    assert restored_df.iloc[0, 0] == 1, "Checkpoint was corrupted by in-place mutation"
