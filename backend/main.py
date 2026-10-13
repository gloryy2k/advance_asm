"""Run from the repository root with python -m backend.main."""

from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from backend.api.health import router as health_router
from backend.api.scope import router as scope_router
from backend.api.scans import router as scan_router
from backend.api.brief import router as brief_router
from backend.api.programs import router as program_router
from backend.config import Settings
from backend.db import Database
from backend.jobs.scope_resolver import ScopeError, ScopeResolver
from backend.jobs.runner import JobRunner
from backend.asm.scheduler import ScanScheduler
from backend.request_logging import install_request_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(app.state.runner.recover)
        app.state.scheduler.start()
        try:
            yield
        finally:
            await app.state.scheduler.close()
            await app.state.runner.close()

    app = FastAPI(title="BBASM", version="0.1.0", lifespan=lifespan)
    install_request_logging(app)
    app.state.settings = settings
    app.state.database = Database(settings.BBASM_DATA / "bbasm.db")
    app.state.scope_resolver = ScopeResolver(settings, app.state.database)
    app.state.runner = JobRunner(settings, app.state.database)
    app.state.scheduler = ScanScheduler(settings, app.state.database, app.state.runner)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"],
    )
    app.include_router(health_router)
    app.include_router(scope_router)
    app.include_router(scan_router)
    app.include_router(brief_router)
    app.include_router(program_router)
    if settings.BBASM_STATIC.is_dir():
        app.mount("/", StaticFiles(directory=settings.BBASM_STATIC, html=True), name="dashboard")

    @app.exception_handler(ScopeError)
    async def scope_error(request, exc):
        return JSONResponse(status_code=422, content={"error": {"code": exc.code, "message": str(exc)}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        message = "; ".join(f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors())
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": message}})

    return app


app = create_app()


if __name__ == "__main__":
    import logging
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    uvicorn.run(app, host=app.state.settings.BBASM_BIND, port=app.state.settings.BBASM_PORT, access_log=False)
