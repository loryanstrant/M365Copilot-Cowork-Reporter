"""Async Microsoft Graph + Azure ARM clients (app-only / client credentials).

One app registration drives all three collectors:

* **Purview audit** — ``AuditLogsQuery.Read.All`` (Cowork event identification)
* **Directory users** — ``User.Read.All`` (org context for chargeback)
* **Azure Cost Management** — an ARM token (``https://management.azure.com``)
  with *Cost Management Reader* on each subscription

Handles token acquisition via MSAL, throttling (429 / ``Retry-After`` with
exponential backoff), and the audit query async job (create -> poll -> page).
"""
from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import msal

logger = logging.getLogger("worker.graph")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_BETA = "https://graph.microsoft.com/beta"
ARM_BASE = "https://management.azure.com"
_GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
_ARM_SCOPE = ["https://management.azure.com/.default"]
_MAX_RETRIES = 6
_MAX_BACKOFF_SECONDS = 60.0


class GraphError(RuntimeError):
    """Raised when Graph/ARM returns an unrecoverable error."""


class GraphAuthError(GraphError):
    """Raised when a client-credentials token cannot be acquired."""


class AppAuth:
    """Acquires app-only tokens (Graph or ARM) using MSAL's token cache."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )

    async def _token(self, scopes: list[str]) -> str:
        result = await asyncio.to_thread(
            self._app.acquire_token_for_client, scopes=scopes
        )
        token = result.get("access_token")
        if not token:
            raise GraphAuthError(
                result.get("error_description")
                or result.get("error")
                or "token acquisition failed"
            )
        return token

    async def graph_token(self) -> str:
        return await self._token(_GRAPH_SCOPE)

    async def arm_token(self) -> str:
        return await self._token(_ARM_SCOPE)


class ApiClient:
    """Thin async wrapper over the Graph + ARM endpoints this project needs."""

    def __init__(
        self, auth: AppAuth, *, concurrency: int = 15, timeout: float = 90.0
    ) -> None:
        self._auth = auth
        self._client = httpx.AsyncClient(timeout=timeout)
        self._sem = asyncio.Semaphore(concurrency)

    async def __aenter__(self) -> "ApiClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- low-level -------------------------------------------------------
    async def _request(
        self,
        method: str,
        url: str,
        *,
        token_kind: str = "graph",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue a request with retry on 429/5xx, honouring ``Retry-After``."""
        for attempt in range(_MAX_RETRIES + 1):
            token = (
                await self._auth.arm_token()
                if token_kind == "arm"
                else await self._auth.graph_token()
            )
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            async with self._sem:
                resp = await self._client.request(
                    method, url, params=params, json=json_body, headers=headers
                )

            if resp.status_code in (429,) or resp.status_code >= 500:
                if attempt >= _MAX_RETRIES:
                    resp.raise_for_status()
                delay = self._retry_delay(resp, attempt)
                logger.warning(
                    "%s %s throttled/errored (attempt %d); retrying in %.1fs",
                    method, resp.status_code, attempt + 1, delay,
                )
                await asyncio.sleep(delay)
                continue

            if resp.status_code >= 400:
                raise GraphError(f"{resp.status_code}: {resp.text[:500]}")
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()
        raise GraphError("exhausted retries")  # pragma: no cover

    @staticmethod
    def _retry_delay(resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return min(2.0**attempt, _MAX_BACKOFF_SECONDS) + random.random()

    async def _paged(
        self, url: str, *, params: dict[str, Any] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield items across all pages, following ``@odata.nextLink``."""
        next_url: str | None = url
        next_params = params
        while next_url:
            data = await self._request("GET", next_url, params=next_params)
            for item in data.get("value", []):
                yield item
            next_url = data.get("@odata.nextLink")
            next_params = None

    # -- connection test -------------------------------------------------
    async def acquire_graph_token(self) -> str:
        return await self._auth.graph_token()

    async def acquire_arm_token(self) -> str:
        return await self._auth.arm_token()

    # -- Purview audit (async query job) --------------------------------
    async def create_audit_query(
        self, start: datetime, end: datetime, *, display_name: str = "cowork-ingest"
    ) -> str:
        """Create a ``CopilotInteraction`` audit query job; return its id."""
        body = {
            "displayName": display_name,
            "filterStartDateTime": _iso(start),
            "filterEndDateTime": _iso(end),
            "operationFilters": ["CopilotInteraction"],
        }
        data = await self._request(
            "POST", f"{GRAPH_BETA}/security/auditLog/queries", json_body=body
        )
        qid = data.get("id")
        if not qid:
            raise GraphError("audit query did not return an id")
        return qid

    async def wait_for_audit_query(
        self, query_id: str, *, poll_seconds: float = 15.0, max_polls: int = 80
    ) -> str:
        """Poll an audit query until it succeeds; return the final status."""
        url = f"{GRAPH_BETA}/security/auditLog/queries/{query_id}"
        for _ in range(max_polls):
            data = await self._request("GET", url)
            status = data.get("status")
            if status == "succeeded":
                return status
            if status == "failed":
                raise GraphError(f"audit query {query_id} failed")
            await asyncio.sleep(poll_seconds)
        raise GraphError(f"audit query {query_id} did not complete in time")

    async def iter_audit_records(
        self, query_id: str, *, page_size: int = 200
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield all records for a completed audit query."""
        url = (
            f"{GRAPH_BETA}/security/auditLog/queries/{query_id}/records"
            f"?$top={page_size}"
        )
        async for item in self._paged(url):
            yield item

    # -- group membership (Entra SSO gating) -----------------------------
    async def check_member_groups(
        self, user_id: str, group_ids: list[str]
    ) -> list[str]:
        """Return which of ``group_ids`` the user is a (transitive) member of."""
        if not group_ids:
            return []
        url = f"{GRAPH_BASE}/users/{user_id}/checkMemberGroups"
        data = await self._request("POST", url, json_body={"groupIds": group_ids})
        return list(data.get("value", []))

    # -- directory users -------------------------------------------------
    async def iter_directory_users(self) -> AsyncIterator[dict[str, Any]]:
        params = {
            "$select": (
                "id,userPrincipalName,mail,userType,jobTitle,companyName,"
                "department,officeLocation,city,state,country,usageLocation,"
                "displayName,givenName,surname,employeeId,employeeType,"
                "accountEnabled,onPremisesExtensionAttributes"
            ),
            "$expand": "manager($select=id,displayName)",
            "$top": 999,
        }
        async for item in self._paged(f"{GRAPH_BASE}/users", params=params):
            yield item

    # -- Azure Cost Management -------------------------------------------
    async def query_cost_by_resource_group(
        self, subscription_id: str, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """POST the Cost Management Query API for daily cost grouped by RG + meter.

        Returns the raw ``columns``/``rows`` payload (reshaped by the caller).
        """
        url = (
            f"{ARM_BASE}/subscriptions/{subscription_id}"
            "/providers/Microsoft.CostManagement/query"
            "?api-version=2024-08-01"
        )
        body = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {"from": _date(start), "to": _date(end)},
            "dataset": {
                "granularity": "Daily",
                "aggregation": {
                    "totalCost": {"name": "PreTaxCost", "function": "Sum"}
                },
                "grouping": [
                    {"type": "Dimension", "name": "ResourceGroupName"},
                    {"type": "Dimension", "name": "ServiceName"},
                    {"type": "Dimension", "name": "Meter"},
                    {"type": "Dimension", "name": "MeterCategory"},
                ],
            },
        }
        return await self._request("POST", url, token_kind="arm", json_body=body)


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _date(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT00:00:00Z")
