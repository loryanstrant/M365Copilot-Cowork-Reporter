"""FastAPI application entrypoint.

Exposes ``/health``, mounts feature routers, and serves the built frontend
bundle in production.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from shared.config import settings
from shared.db import engine

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("api")


async def _seed_admin_from_env() -> None:
    """Create a first admin from ADMIN_USERNAME/ADMIN_PASSWORD when no users exist."""
    if not (settings.admin_username and settings.admin_password):
        return
    from sqlalchemy import func, select

    from shared.db import SessionLocal
    from shared.models import AppUser
    from shared.security import hash_password

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(AppUser))
        if count:
            return
        session.add(
            AppUser(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role="admin",
            )
        )
        await session.commit()
        logger.info("Seeded initial admin user '%s'.", settings.admin_username)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run database migrations to head before serving traffic."""
    if os.getenv("RUN_MIGRATIONS_ON_STARTUP", "true").lower() != "false":
        try:
            from shared.migrate import upgrade_to_head

            upgrade_to_head()
        except Exception as exc:
            # Do not swallow this. Alembic runs the chain in one transaction, so
            # a mid-chain failure rolls the whole thing back and leaves the
            # database with no tables at all. Carrying on would serve a healthy
            # looking app over an empty schema, which is far harder to diagnose
            # than refusing to start.
            logger.error("Migration on startup failed: %s", exc)
            raise
    try:
        await _seed_admin_from_env()
    except Exception as exc:  # pragma: no cover - startup diagnostics
        logger.error("Admin seeding failed: %s", exc)
    yield


app = FastAPI(
    title="M365 Copilot Cowork Reporter",
    version="0.1.0",
    description=(
        "Reports Microsoft 365 Copilot Cowork consumption (Azure cost + credits) "
        "and usage (tasks/adoption + Purview audit events)."
    ),
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
async def health() -> JSONResponse:
    """Liveness/readiness probe: 200 only when the database is usable.

    ``SELECT 1`` alone is not enough. It succeeds against a completely empty
    database, so an instance whose migrations never ran would report healthy
    while every route that touches a table returns 500 — which is exactly how
    issue #3 stayed invisible. Check that the schema is actually there.
    """
    db_ok = False
    schema_ok = False
    detail = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_ok = True
            # app_config is created by the very first migration, so its absence
            # means the schema was never built.
            await conn.execute(text("SELECT 1 FROM app_config LIMIT 1"))
            schema_ok = True
    except Exception as exc:  # pragma: no cover
        if db_ok:
            detail = (
                "database reachable but schema is missing — migrations have not "
                f"run: {exc}"
            )
        else:
            detail = f"database unavailable: {exc}"
        logger.warning("Health check failed: %s", detail)

    healthy = db_ok and schema_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "database": db_ok,
            "schema": schema_ok,
            "environment": settings.app_env,
            "detail": detail,
        },
    )


def _register_routers() -> None:
    from api.routers import admin, auth, metrics, upload

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(metrics.router)
    app.include_router(metrics.common_router)
    app.include_router(metrics.me_router)
    app.include_router(upload.router)


_register_routers()


def _mount_frontend() -> None:
    """Serve the built SPA bundle when it exists (production single-container)."""
    dist = settings.frontend_dist
    index_path = os.path.join(dist, "index.html")
    if not os.path.isfile(index_path):
        logger.info("Frontend bundle not found at %s (dev mode)", dist)
        return

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    # Cache policy, and why it is split.
    #
    # Vite gives every asset a content hash in its filename, so an asset URL
    # never changes meaning: it can be cached forever. index.html is the
    # opposite — its URL never changes but its contents do, because it names
    # the current hashed bundle.
    #
    # Serving index.html with no cache directive at all (which is what this
    # did) lets the browser apply its own heuristic and hold on to it. The
    # result is an upgraded deployment where the server has the new bundle,
    # says so correctly, and the browser keeps asking for the old one it still
    # remembers — indistinguishable, from the outside, from a deploy that
    # silently failed.
    ASSET_CACHE = "public, max-age=31536000, immutable"
    HTML_CACHE = "no-cache"  # revalidate every time; the file is ~0.5 KB

    class ImmutableAssets(StaticFiles):
        async def get_response(self, path: str, scope):
            response = await super().get_response(path, scope)
            if response.status_code == 200:
                response.headers["Cache-Control"] = ASSET_CACHE
            return response

    assets_dir = os.path.join(dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", ImmutableAssets(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        candidate = os.path.join(dist, full_path)
        if full_path and os.path.isfile(candidate):
            # Files served from the bundle root (favicon, logos, the suite
            # thumbnails) keep their names across releases, so they have to
            # revalidate too or a refreshed logo never arrives.
            return FileResponse(candidate, headers={"Cache-Control": HTML_CACHE})
        return FileResponse(index_path, headers={"Cache-Control": HTML_CACHE})

    logger.info("Serving frontend bundle from %s", dist)


_mount_frontend()
