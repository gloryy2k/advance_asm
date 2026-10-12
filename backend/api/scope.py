"""Resolve only: the review/launch APIs are implemented in later phases."""

from fastapi import APIRouter, Request

from backend.models import ResolveRequest, ResolveResponse

router = APIRouter(prefix="/api/scope", tags=["scope"])


@router.post("/resolve", response_model=ResolveResponse)
def resolve_scope(body: ResolveRequest, request: Request):
    request.app.state.database.migrate()
    return request.app.state.scope_resolver.resolve(body)
