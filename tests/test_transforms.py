"""Cowork identification + transform tests — the load-bearing logic."""
from __future__ import annotations

from worker.transforms import (
    is_cowork_event,
    transform_cost_rows,
    transform_cowork_event,
)

# A real-shaped Cowork audit record (mirrors live Avanoso data).
COWORK_RECORD = {
    "id": "evt-1",
    "createdDateTime": "2026-09-01T07:25:57Z",
    "userPrincipalName": "loryan.strant@avanoso.com",
    "auditData": {
        "Operation": "CopilotInteraction",
        "AppIdentity": "Copilot.M365Copilot.CoworkChat",
        "AgentName": "Copilot Cowork",
        "UserId": "loryan.strant@avanoso.com",
        "CopilotEventData": {
            "AppHost": "cowork",
            "ThreadId": "19:thread@thread.v2",
            "AISystemPlugin": [{"Id": "tool_search_tool", "Name": "tool_search_tool"}],
            "AccessedResources": [],
            "Messages": [
                {"Id": "1", "isPrompt": True},
                {"Id": "2", "isPrompt": False},
            ],
        },
    },
}

BIZCHAT_RECORD = {
    "id": "evt-2",
    "auditData": {
        "Operation": "CopilotInteraction",
        "AppIdentity": "Copilot.M365Copilot.Bizchat",
        "CopilotEventData": {"AppHost": "Office"},
    },
}


def test_cowork_record_is_identified():
    assert is_cowork_event(COWORK_RECORD) is True


def test_bizchat_record_is_not_cowork():
    assert is_cowork_event(BIZCHAT_RECORD) is False


def test_identification_by_app_identity_only():
    rec = {"id": "x", "auditData": {"AppIdentity": "Copilot.M365Copilot.CoworkChat"}}
    assert is_cowork_event(rec) is True


def test_transform_cowork_event_extracts_fields():
    row = transform_cowork_event(COWORK_RECORD)
    assert row is not None
    assert row["event_id"] == "evt-1"
    assert row["app_host"] == "cowork"
    assert row["agent_name"] == "Copilot Cowork"
    assert row["thread_id"] == "19:thread@thread.v2"
    assert row["tools"] == ["tool_search_tool"]
    assert row["prompt_message_count"] == 1
    assert row["response_message_count"] == 1
    # Prompt text is never captured.
    assert "prompt_text" not in row


def test_transform_cost_rows_reshapes_columns_and_rows():
    payload = {
        "properties": {
            "columns": [
                {"name": "PreTaxCost"},
                {"name": "ResourceGroupName"},
                {"name": "ServiceName"},
                {"name": "Meter"},
                {"name": "MeterCategory"},
                {"name": "UsageDate"},
                {"name": "Currency"},
            ],
            "rows": [
                [12.5, "RG-Copilot", "Copilot", "Credits", "Copilot", 20260901, "AUD"],
                [3.0, "RG-Copilot", "Copilot", "Credits", "Copilot", 20260831, "AUD"],
            ],
        }
    }
    rows = transform_cost_rows("sub-1", payload)
    assert len(rows) == 2
    r = rows[0]
    assert r["subscription_id"] == "sub-1"
    assert r["resource_group"] == "rg-copilot"  # lowercased
    assert r["cost"] == 12.5
    assert r["currency"] == "AUD"
    assert str(r["cost_date"]) == "2026-09-01"
