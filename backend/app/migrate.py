"""Apply database migrations at startup (and seed default plans/settings)."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .db import SessionLocal, engine

ROOT = Path(__file__).resolve().parents[1]


def upgrade() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.attributes["skip_logging_config"] = True
    tables = set(inspect(engine).get_table_names())
    # Databases created before migrations were wired in (create_all) start at the initial schema.
    if "users" in tables and "alembic_version" not in tables:
        command.stamp(cfg, "0001")
    command.upgrade(cfg, "head")
    from .billing import seed
    with SessionLocal() as db:
        seed(db)
