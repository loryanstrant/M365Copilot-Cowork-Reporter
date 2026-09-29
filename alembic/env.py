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

if config.config_file_name is not None:
    # disable_existing_loggers=False matters when this runs in-process on API
    # startup rather than from the alembic CLI. The default (True) switches off
    # every logger configured before it — including uvicorn's — so the app goes
    # silent from "Running database migrations" onwards: no "Application
    # startup complete", no access logs, nothing. It reads exactly like a hang
    # at startup, and it cost a verification session an hour chasing one.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

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
