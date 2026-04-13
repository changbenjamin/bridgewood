from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
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

    Base.metadata.create_all(bind=engine)
    _ensure_runtime_schema()


def _ensure_runtime_schema() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("users"):
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    statements: list[str] = []

    if "account_api_key_hash" not in user_columns:
        statements.append("ALTER TABLE users ADD COLUMN account_api_key_hash VARCHAR(64)")
    if "account_api_key_prefix" not in user_columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN account_api_key_prefix VARCHAR(16)"
        )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_account_api_key_hash "
                "ON users (account_api_key_hash)"
            )
        )
