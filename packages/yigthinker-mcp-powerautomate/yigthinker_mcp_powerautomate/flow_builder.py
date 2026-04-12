"""Notification-only Flow clientdata builder for pa_deploy_flow.

Builds a fixed HTTP Trigger -> Send Email (V2) Flow Definition JSON object
from a pure function. No file I/O, no network — fully unit-testable in-process.

Design spec section 6.1 explicitly marks this notification-only shape as reliable.
Complex orchestration stays in Phase 9 guided mode.
"""
from __future__ import annotations


def build_notification_flow_clientdata(
    flow_name: str,
    recipients: list[str],
    subject_template: str = "{workflow_name} notification",
    display_name: str | None = None,
) -> dict:
    """Build the Dataverse ``clientdata`` JSON for a notification Flow.

    Returns a dict suitable for ``json.dumps()`` and submission to the
    Flow Management API ``POST /flows`` endpoint.
    """
    raise NotImplementedError("Plan 12-04 replaces this")
