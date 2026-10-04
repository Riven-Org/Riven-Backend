from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from riven_api import models  # noqa: F401  (registers tables on Base.metadata)
from riven_api.config import get_settings
from riven_api.db import create_tables, get_engine, seed_demo_user
from riven_api.routers import auth, health


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await create_tables(get_engine())
    await seed_demo_user(get_engine())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Riven API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    return app


app = create_app()
