"""Request logs intentionally omit bodies, query strings and credentials."""
import json
import logging
from time import perf_counter
from uuid import uuid4

from fastapi.responses import JSONResponse


def install_request_logging(app):
    logger = logging.getLogger("bbasm.requests")

    @app.middleware("http")
    async def request_log(request, call_next):
        started, request_id = perf_counter(), uuid4().hex
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(json.dumps({"event": "request_error", "request_id": request_id, "exception_type": type(exc).__name__}))
            response = JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Internal server error"}})
        route = request.scope.get("route")
        logger.info(json.dumps({"event": "request", "request_id": request_id,
                               "method": request.method, "route": getattr(route, "path", "unmatched"),
                               "status": response.status_code, "duration_ms": round((perf_counter() - started) * 1000, 2)}))
        response.headers["X-Request-ID"] = request_id
        return response
