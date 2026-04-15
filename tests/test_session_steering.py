from yigthinker.session import SessionContext


def test_steering_queue_exists_on_session():
    ctx = SessionContext()
    assert hasattr(ctx, "_steering_queue")


def test_steer_adds_to_queue():
    ctx = SessionContext()
    ctx.steer("change direction")
    assert len(ctx._steering_queue) > 0


def test_drain_steerings_returns_messages():
    ctx = SessionContext()
    ctx.steer("msg1")
    ctx.steer("msg2")
    drained = ctx.drain_steerings()
    assert len(drained) == 2
    assert drained[0] == "msg1"
    assert drained[1] == "msg2"
    assert len(ctx._steering_queue) == 0


def test_drain_steerings_empty_returns_empty_list():
    ctx = SessionContext()
    assert ctx.drain_steerings() == []


def test_is_running_default_false():
    ctx = SessionContext()
    assert ctx._is_running is False
