import pytest
from yigthinker.settings import DEFAULT_SETTINGS
from yigthinker.session import SessionContext

@pytest.fixture
def default_settings():
    return dict(DEFAULT_SETTINGS)

@pytest.fixture
def session(default_settings):
    return SessionContext(settings=default_settings)
