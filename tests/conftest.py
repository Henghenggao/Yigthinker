import os
import sys

import pytest
from yigthinker.settings import DEFAULT_SETTINGS
from yigthinker.session import SessionContext

@pytest.fixture
def default_settings():
    return dict(DEFAULT_SETTINGS)

@pytest.fixture
def session(default_settings):
    return SessionContext(settings=default_settings)


def pytest_sessionfinish(session, exitstatus):
    """Force interpreter exit after pytest reporting completes.

    Why: kaleido >= 1.0 (used by ChartExporter.to_png tests) spawns a long-
    lived Chrome subprocess that is kept alive for reuse. On CI runners the
    atexit teardown occasionally hangs waiting on that subprocess' stdio to
    close, causing pytest to print the summary and then sit idle for the
    entire step budget (observed: 8 min post-summary hang before step
    timeout fires).

    Bypassing the normal interpreter shutdown with ``os._exit`` orphans the
    Chrome subprocess, which the OS reaps immediately. We only do this when
    running under CI (``CI=true`` is set by GitHub Actions) so local dev
    loops keep the normal shutdown path and any debuggers attached.
    """
    if os.environ.get("CI") == "true":
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exitstatus)
