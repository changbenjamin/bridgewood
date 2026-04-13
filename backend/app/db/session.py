from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

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

    Base.metadata.create_all(bind=engine)


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
