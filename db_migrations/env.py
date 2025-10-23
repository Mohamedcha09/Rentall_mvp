from __future__ import annotations
from logging.config import fileConfig
import os
from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv
load_dotenv()
# Render يمرّر DATABASE_URL تلقائيًا من خدمة PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_FULL")

config = context.config
if DATABASE_URL:
    config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# لا نستخدم autogenerate الآن
target_metadata = None

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()