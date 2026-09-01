"""CSV upload routes for the two admin-centre exports with no API.

Admins export the Cowork usage report and the Cost Management / Credits report
from the M365 admin centre and upload them here. Parsing is tolerant of header
variants and idempotent on each table's natural key.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_admin
from api.schemas import UploadResultOut
from shared.db import get_session
from worker.csv_import import (
    CsvImportError,
    import_cowork_usage,
    import_credit_consumption,
)

logger = logging.getLogger("api.upload")

router = APIRouter(
    prefix="/admin/upload", tags=["upload"], dependencies=[Depends(require_admin)]
)

_MAX_BYTES = 20 * 1024 * 1024  # 20 MB is far more than any admin export


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


@router.post("/cowork-usage", response_model=UploadResultOut)
async def upload_cowork_usage(
    file: UploadFile = File(...),
    report_period: int | None = Form(None),
    report_refresh_date: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> UploadResultOut:
    """Upload an admin-centre **Cowork usage report** CSV."""
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large.")
    try:
        result = await import_cowork_usage(
            session, content,
            report_period=report_period,
            report_refresh_date=_parse_date(report_refresh_date),
        )
    except CsvImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadResultOut(**result)


@router.post("/credit-consumption", response_model=UploadResultOut)
async def upload_credit_consumption(
    file: UploadFile = File(...),
    scope_type: str = Form("user"),
    as_of_date: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> UploadResultOut:
    """Upload an admin-centre **Cost Management / Credits** CSV.

    ``scope_type`` selects the export shape: user | service | group | summary.
    """
    if scope_type not in {"user", "service", "group", "summary"}:
        raise HTTPException(status_code=400, detail="Invalid scope_type.")
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large.")
    try:
        result = await import_credit_consumption(
            session, content,
            scope_type=scope_type,
            as_of_date=_parse_date(as_of_date),
        )
    except CsvImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadResultOut(**result)
