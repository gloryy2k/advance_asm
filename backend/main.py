"""Run from the repository root with python -m backend.main."""

from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from backend.api.health import router as health_router
from backend.api.tools import router as tools_router
from backend.api.scope import router as scope_router
from backend.api.scans import router as scan_router
from backend.api.brief import router as brief_router
from backend.api.programs import router as program_router
from backend.api.profiles import router as profile_router
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
        # Upgrade (with an automatic backup) before serving anything: read endpoints must never see an old schema.
        # A brand-new install still creates its database lazily (health stays fail-soft on missing paths).
        if app.state.database.path.exists():
            await asyncio.to_thread(app.state.database.migrate)
        await asyncio.to_thread(app.state.runner.recover)
        await asyncio.to_thread(app.state.templates.recover)
        mode = settings.BBASM_UPDATE_TEMPLATES.strip().lower()
        if mode == "1" or (mode == "auto" and not app.state.templates.describe()["installed"]):
            try:
                app.state.templates.start_update()      # background; its state is visible on the Tools page
            except ScopeError:
                pass                                   # nuclei not installed, or an update is already running
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
    from backend.templates import TemplateStore
    app.state.templates = TemplateStore(settings)
    app.state.scheduler = ScanScheduler(settings, app.state.database, app.state.runner)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"],
    )
    app.include_router(health_router)
    app.include_router(tools_router)
    app.include_router(scope_router)
    app.include_router(scan_router)
    app.include_router(brief_router)
    app.include_router(program_router)
    app.include_router(profile_router)
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
