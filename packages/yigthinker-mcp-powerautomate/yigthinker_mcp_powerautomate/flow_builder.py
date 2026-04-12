"""Notification-only Flow clientdata builder for pa_deploy_flow.

Builds a fixed HTTP Trigger -> Send Email (V2) Flow Definition JSON object
from a pure function. No file I/O, no network -- fully unit-testable in-process.

Design spec section 6.1 explicitly marks this notification-only shape as reliable.
Complex orchestration stays in Phase 9 guided mode.

CONTEXT.md D-19/D-20: Fixed dict template embedded directly in the function.
Parallels Phase 11 nupkg.py verbatim template pattern.
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

    Args:
        flow_name: Internal flow identifier used for the API call.
        recipients: List of email addresses for the To field.
        subject_template: Subject line template; ``{workflow_name}`` is
            replaced with *display_name* (or *flow_name* if not given).
        display_name: Human-readable name shown in the email subject.
            Falls back to *flow_name* when ``None``.

    Returns:
        A JSON-serializable dict in the Dataverse clientdata envelope
        format with ``properties``, ``connectionReferences``,
        ``definition``, and ``schemaVersion``.
    """
    display = display_name or flow_name
    subject = subject_template.replace("{workflow_name}", display)
    to_field = ";".join(recipients)

    return {
        "properties": {
            "connectionReferences": {
                "shared_office365": {
                    "runtimeSource": "embedded",
                    "connection": {},
                    "api": {"name": "shared_office365"},
                },
            },
            "definition": {
                "$schema": (
                    "https://schema.management.azure.com/providers/"
                    "Microsoft.Logic/schemas/2016-06-01/"
                    "workflowdefinition.json#"
                ),
                "contentVersion": "1.0.0.0",
                "parameters": {
                    "$connections": {
                        "defaultValue": {},
                        "type": "Object",
                    },
                    "$authentication": {
                        "defaultValue": {},
                        "type": "SecureObject",
                    },
                },
                "triggers": {
                    "manual": {
                        "type": "Request",
                        "kind": "Http",
                        "inputs": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "workflow_name": {"type": "string"},
                                    "status": {"type": "string"},
                                    "message": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "actions": {
                    "Send_an_email_(V2)": {
                        "runAfter": {},
                        "type": "OpenApiConnection",
                        "inputs": {
                            "host": {
                                "apiId": (
                                    "/providers/Microsoft.PowerApps"
                                    "/apis/shared_office365"
                                ),
                                "connectionName": "shared_office365",
                                "operationId": "SendEmailV2",
                            },
                            "parameters": {
                                "emailMessage/To": to_field,
                                "emailMessage/Subject": subject,
                                "emailMessage/Body": (
                                    "<p>Workflow: "
                                    "@{triggerBody()?['workflow_name']}"
                                    "<br>"
                                    "Status: "
                                    "@{triggerBody()?['status']}"
                                    "<br>"
                                    "Message: "
                                    "@{triggerBody()?['message']}"
                                    "</p>"
                                ),
                            },
                            "authentication": (
                                "@parameters('$authentication')"
                            ),
                        },
                    },
                },
            },
        },
        "schemaVersion": "1.0.0.0",
    }
