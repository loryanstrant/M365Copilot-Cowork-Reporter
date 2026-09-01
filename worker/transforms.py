"""Pure transforms: raw Graph/ARM payloads -> ORM row dicts.

No I/O here — deterministic and unit-testable. Cowork identification lives in
:func:`is_cowork_event`, validated live against the Avanoso tenant.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

# Cowork fingerprints (from live Avanoso audit data).
_COWORK_APP_HOST = "cowork"
_COWORK_APP_IDENTITY = "Copilot.M365Copilot.CoworkChat"


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _copilot_event_data(audit_data: dict[str, Any]) -> dict[str, Any]:
    return audit_data.get("CopilotEventData") or {}


def is_cowork_event(record: dict[str, Any]) -> bool:
    """True when an audit ``CopilotInteraction`` record is a Cowork interaction.

    A row is Cowork when ``CopilotEventData.AppHost == 'cowork'`` OR
    ``AppIdentity == 'Copilot.M365Copilot.CoworkChat'`` (case-insensitive).
    """
    audit = record.get("auditData") or {}
    app_identity = (audit.get("AppIdentity") or "").strip().lower()
    app_host = (_copilot_event_data(audit).get("AppHost") or "").strip().lower()
    return (
        app_host == _COWORK_APP_HOST
        or app_identity == _COWORK_APP_IDENTITY.lower()
    )


def transform_cowork_event(record: dict[str, Any]) -> dict[str, Any] | None:
    """Map an audit record to a ``fact_cowork_event`` row dict."""
    audit = record.get("auditData") or {}
    ced = _copilot_event_data(audit)
    event_id = record.get("id") or audit.get("Id")
    if not event_id:
        return None

    messages = ced.get("Messages") or []
    prompt_count = sum(1 for m in messages if m.get("isPrompt"))
    response_count = sum(1 for m in messages if m.get("isPrompt") is False)

    tools = [
        p.get("Name") or p.get("Id")
        for p in (ced.get("AISystemPlugin") or [])
        if isinstance(p, dict)
    ]

    return {
        "event_id": str(event_id),
        "created_at": _parse_dt(record.get("createdDateTime"))
        or _parse_dt(audit.get("CreationTime")),
        "user_id": audit.get("UserId") or record.get("userId"),
        "user_principal_name": record.get("userPrincipalName")
        or audit.get("UserId"),
        "operation": audit.get("Operation") or record.get("operation"),
        "app_host": ced.get("AppHost"),
        "app_identity": audit.get("AppIdentity"),
        "agent_name": audit.get("AgentName"),
        "thread_id": ced.get("ThreadId"),
        "client_ip": audit.get("ClientIP"),
        "tools": tools or None,
        "accessed_resources": ced.get("AccessedResources") or None,
        "prompt_message_count": prompt_count or None,
        "response_message_count": response_count or None,
        "raw_json": record,
    }


def transform_directory_user(user: dict[str, Any]) -> dict[str, Any]:
    """Map a Graph user to a ``dim_user`` row dict."""
    manager = user.get("manager") or {}
    ext = user.get("onPremisesExtensionAttributes") or {}
    row: dict[str, Any] = {
        "user_id": user.get("id"),
        "upn": user.get("userPrincipalName"),
        "email": user.get("mail"),
        "display_name": user.get("displayName"),
        "given_name": user.get("givenName"),
        "surname": user.get("surname"),
        "job_title": user.get("jobTitle"),
        "company_name": user.get("companyName"),
        "department": user.get("department"),
        "office_location": user.get("officeLocation"),
        "city": user.get("city"),
        "state": user.get("state"),
        "country": user.get("country"),
        "usage_location": user.get("usageLocation"),
        "employee_id": user.get("employeeId"),
        "employee_type": user.get("employeeType"),
        "manager_id": manager.get("id"),
        "manager_name": manager.get("displayName"),
        "account_enabled": user.get("accountEnabled"),
        "user_type": user.get("userType"),
    }
    for i in range(1, 16):
        row[f"ext{i}"] = ext.get(f"extensionAttribute{i}")
    return row


def is_included_directory_user(user: dict[str, Any]) -> bool:
    """Keep enabled member users (skip guests and disabled accounts)."""
    if user.get("userType") == "Guest":
        return False
    if user.get("accountEnabled") is False:
        return False
    return bool(user.get("id"))


def _column_index(columns: list[dict[str, Any]]) -> dict[str, int]:
    return {c.get("name"): i for i, c in enumerate(columns)}


def _cost_date(raw: Any) -> date | None:
    """Cost Management returns UsageDate as an int like 20260901 or an ISO str."""
    if raw is None:
        return None
    if isinstance(raw, int):
        s = str(raw)
        if len(s) == 8:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    dt = _parse_dt(str(raw))
    return dt.date() if dt else None


def transform_cost_rows(
    subscription_id: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """Reshape a Cost Management ``columns``/``rows`` payload into row dicts.

    ``Table.FromRows`` equivalent: the API returns positional rows, not records.
    """
    props = payload.get("properties", payload)
    columns = props.get("columns") or []
    rows = props.get("rows") or []
    idx = _column_index(columns)

    cost_key = "PreTaxCost" if "PreTaxCost" in idx else "Cost"
    out: list[dict[str, Any]] = []
    for row in rows:
        def get(name: str) -> Any:
            i = idx.get(name)
            return row[i] if i is not None and i < len(row) else None

        cost_date = _cost_date(get("UsageDate"))
        if cost_date is None:
            continue
        out.append({
            "cost_date": cost_date,
            "subscription_id": subscription_id,
            "resource_group": (get("ResourceGroupName") or "").lower() or None,
            "service_name": get("ServiceName"),
            "meter_category": get("MeterCategory"),
            "meter_name": get("Meter") or get("MeterName"),
            "cost": float(get(cost_key) or 0),
            "currency": get("Currency"),
        })
    return out


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
