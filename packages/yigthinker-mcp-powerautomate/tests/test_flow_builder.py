"""Structural unit tests for flow_builder.build_notification_flow_clientdata.

Verifies CONTEXT.md D-19/D-20/D-21: pure function returning a dict with
HTTP Trigger -> Send Email (V2) Flow Definition in the clientdata format.
"""
from __future__ import annotations

import json

from yigthinker_mcp_powerautomate.flow_builder import (
    build_notification_flow_clientdata,
)


def test_returns_dict_with_properties_and_schema_version():
    result = build_notification_flow_clientdata("test-flow", ["a@b.com"])
    assert isinstance(result, dict)
    assert "properties" in result
    assert result["schemaVersion"] == "1.0.0.0"


def test_http_trigger_present():
    result = build_notification_flow_clientdata("test-flow", ["a@b.com"])
    triggers = result["properties"]["definition"]["triggers"]
    assert "manual" in triggers
    assert triggers["manual"]["type"] == "Request"
    assert triggers["manual"]["kind"] == "Http"


def test_send_email_v2_action_present():
    result = build_notification_flow_clientdata("test-flow", ["a@b.com"])
    actions = result["properties"]["definition"]["actions"]
    assert "Send_an_email_(V2)" in actions
    action = actions["Send_an_email_(V2)"]
    assert action["type"] == "OpenApiConnection"
    assert action["inputs"]["host"]["operationId"] == "SendEmailV2"


def test_recipient_in_to_field():
    result = build_notification_flow_clientdata(
        "test-flow", ["user@example.com"],
    )
    action = result["properties"]["definition"]["actions"]["Send_an_email_(V2)"]
    to_field = action["inputs"]["parameters"]["emailMessage/To"]
    assert "user@example.com" in to_field


def test_multiple_recipients_semicolon_separated():
    result = build_notification_flow_clientdata(
        "test-flow", ["a@b.com", "c@d.com"],
    )
    action = result["properties"]["definition"]["actions"]["Send_an_email_(V2)"]
    to_field = action["inputs"]["parameters"]["emailMessage/To"]
    assert to_field == "a@b.com;c@d.com"


def test_subject_template_applied():
    result = build_notification_flow_clientdata(
        "my-flow", ["a@b.com"],
        subject_template="Alert: {workflow_name}",
    )
    action = result["properties"]["definition"]["actions"]["Send_an_email_(V2)"]
    subject = action["inputs"]["parameters"]["emailMessage/Subject"]
    assert subject == "Alert: my-flow"


def test_display_name_overrides_flow_name_in_subject():
    result = build_notification_flow_clientdata(
        "internal-id", ["a@b.com"],
        display_name="Pretty Name",
    )
    action = result["properties"]["definition"]["actions"]["Send_an_email_(V2)"]
    subject = action["inputs"]["parameters"]["emailMessage/Subject"]
    assert "Pretty Name notification" in subject


def test_connection_reference_for_office365():
    result = build_notification_flow_clientdata("test-flow", ["a@b.com"])
    conn_refs = result["properties"]["connectionReferences"]
    assert "shared_office365" in conn_refs
    assert conn_refs["shared_office365"]["api"]["name"] == "shared_office365"


def test_output_is_json_serializable():
    result = build_notification_flow_clientdata(
        "test-flow", ["a@b.com", "c@d.com"],
        subject_template="Alert: {workflow_name}",
        display_name="My Flow",
    )
    # Must not raise
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
    assert len(serialized) > 0


def test_definition_schema_url():
    result = build_notification_flow_clientdata("test-flow", ["a@b.com"])
    schema = result["properties"]["definition"]["$schema"]
    assert "Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json" in schema
