from pathlib import Path
from collections.abc import Generator

import alembic.command as alembic_command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
ROOT_DIR = Path(__file__).resolve().parents[3]
ALEMBIC_INI_PATH = ROOT_DIR / "alembic.ini"
BASELINE_REVISION = "20260413_01"

connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import entities  # noqa: F401

    if _legacy_schema_present():
        _drop_all_tables()

    _run_migrations()


def _run_migrations() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    alembic_config = _build_alembic_config()

    if not table_names:
        alembic_command.upgrade(alembic_config, "head")
        return

    if "alembic_version" in table_names:
        alembic_command.upgrade(alembic_config, "head")
        return

    if _matches_baseline_schema(inspector):
        alembic_command.stamp(alembic_config, BASELINE_REVISION)
        alembic_command.upgrade(alembic_config, "head")
        return

    if _matches_head_schema(inspector):
        alembic_command.stamp(alembic_config, "head")
        return

    raise RuntimeError(
        "Database schema exists but is not managed by Alembic. Manual migration required."
    )


def _build_alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    config.set_main_option("script_location", str(ROOT_DIR / "backend/alembic"))
    return config


def _legacy_schema_present() -> bool:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "trades" in table_names:
        return True
    if "activity_log" in table_names:
        return True
    if "users" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if {
            "alpaca_api_key",
            "alpaca_secret_key",
            "alpaca_base_url",
        }.intersection(user_columns):
            return True
    if "agents" in table_names:
        agent_columns = {column["name"] for column in inspector.get_columns("agents")}
        if "real_money" in agent_columns or "is_paper" in agent_columns:
            return True
    return False


def _drop_all_tables() -> None:
    reflected = MetaData()
    reflected.reflect(bind=engine)
    reflected.drop_all(bind=engine)


def _matches_baseline_schema(inspector) -> bool:
    required_tables = {
        "users",
        "agents",
        "executions",
        "positions",
        "portfolio_snapshots",
        "benchmark_state",
        "benchmark_snapshots",
    }
    table_names = set(inspector.get_table_names())
    if not required_tables.issubset(table_names):
        return False

    agent_columns = {column["name"] for column in inspector.get_columns("agents")}
    return "is_active" not in agent_columns and "deactivated_at" not in agent_columns


def _matches_head_schema(inspector) -> bool:
    required_tables = {
        "users",
        "agents",
        "executions",
        "positions",
        "portfolio_snapshots",
        "benchmark_state",
        "benchmark_snapshots",
    }
    table_names = set(inspector.get_table_names())
    if not required_tables.issubset(table_names):
        return False

    agent_columns = {column["name"] for column in inspector.get_columns("agents")}
    return {"is_active", "deactivated_at"}.issubset(agent_columns)
