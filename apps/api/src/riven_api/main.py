from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from riven_api.config import get_settings
from riven_api.routers import health
from riven_schemas import SCHEMA_VERSION


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Riven API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)

    @app.get("/v1/meta")
    async def meta() -> dict[str, str]:
        return {"env": settings.env, "schema_version": SCHEMA_VERSION}

    return app


app = create_app()
