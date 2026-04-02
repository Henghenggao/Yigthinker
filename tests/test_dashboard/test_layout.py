from yigthinker.dashboard.layout import create_dash_app


def test_dash_app_creates():
    """Smoke test: Dash app initializes without error."""
    app = create_dash_app()
    assert app is not None
    assert app.layout is not None
