"""Alembic environment.

Runs migrations synchronously using the psycopg3 driver. The async app URL
(``postgresql+psycopg://``) works for a synchronous engine too, so we reuse
``DATABASE_URL`` directly.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from shared.config import settings
from shared.db import Base

# Import models so their tables register on Base.metadata.
import shared.models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

# Only configure logging when Alembic is driving — i.e. from the CLI, where
# nothing else has set logging up and the ini file is the only source of it.
#
# In-process this must not run at all. shared.migrate calls this during FastAPI
# startup, by which point uvicorn and the app have configured logging, and
# fileConfig would overwrite it: it replaces the root logger's handlers and
# forces its level to alembic.ini's `logger_root level = WARNING`. The visible
# result is an app that goes silent from "Running database migrations to
# head..." onwards — no "Application startup complete", no access lines, and no
# INFO from any app logger for the life of the process — while actually serving
# fine. disable_existing_loggers=False is not enough on its own: it stops
# existing loggers being muted, but the root reset still happens.
#
# shared.migrate.upgrade_to_head sets this attribute; the CLI never does.
if config.config_file_name is not None and not config.attributes.get(
    "in_process", False
):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
