from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.db.session import SessionLocal, init_db
from app.services.broadcaster import ConnectionManager
from app.services.rate_limit import InMemoryRateLimiter
from app.workers.price_feed import PriceFeedService
from app.workers.snapshot_worker import SnapshotWorker


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    connection_manager = ConnectionManager()
    price_feed_service = PriceFeedService(
        SessionLocal, connection_manager, settings.price_refresh_seconds
    )
    snapshot_worker = SnapshotWorker(
        SessionLocal, price_feed_service, settings.snapshot_interval_minutes
    )
    rate_limiter = InMemoryRateLimiter(
        {
            "signup": (
                settings.signup_rate_limit,
                settings.signup_rate_limit_window_seconds,
            ),
            "agent_create": (
                settings.agent_create_rate_limit,
                settings.agent_create_rate_limit_window_seconds,
            ),
            "execution_report": (
                settings.execution_report_rate_limit,
                settings.execution_report_rate_limit_window_seconds,
            ),
        }
    )

    app.state.connection_manager = connection_manager
    app.state.price_feed_service = price_feed_service
    app.state.snapshot_worker = snapshot_worker
    app.state.rate_limiter = rate_limiter

    price_feed_service.start()
    snapshot_worker.start()
    try:
        yield
    finally:
        await snapshot_worker.stop()
        await price_feed_service.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_v1_prefix)
