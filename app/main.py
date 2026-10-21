from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.cache import Cache, make_cache
from app.config import Settings, get_settings
from app.db import Database
from app.routes import router

STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, cache: Cache | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.db = Database(settings.database_url)
        app.state.cache = cache or make_cache(settings.redis_url)
        await app.state.db.create_tables()
        yield
        await app.state.cache.close()
        await app.state.db.dispose()

    app = FastAPI(title="Короткие ссылки", version="1.0.0", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.include_router(router)
    return app


app = create_app()
