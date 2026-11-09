"""OpenAI 兼容入口。错误体不用业务信封。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.errors import AppError
from app.core.messages_en import MESSAGE_BY_CODE_EN
from app.core.request_ip import client_ip
from app.gateway.limit import MemoryRateLimiter, MemorySlots
from app.gateway.service import GatewayService, closed_path
from app.keys.cache import MemoryKeyCache

router = APIRouter(tags=["gateway"])


def _openai(exc: AppError) -> JSONResponse:
    kinds = {
        400: "invalid_request_error",
        401: "authentication_error",
        402: "insufficient_quota",
        403: "permission_error",
        404: "invalid_request_error",
        429: "rate_limit_error",
        502: "upstream_error",
        503: "api_error",
    }
    # OpenAI 兼容客户端面向机器/SDK，统一英文 message；业务码仍放 code。
    message = MESSAGE_BY_CODE_EN.get(exc.code) or exc.code
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"message": message, "type": kinds.get(exc.status_code, "api_error"), "code": exc.code}},
    )


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise AppError(401, "INVALID_API_KEY")
    return header.split(" ", 1)[1].strip()


def _service(request: Request, session: Any) -> GatewayService:
    cache = getattr(request.app.state, "key_cache", None)
    if cache is None:
        cache = MemoryKeyCache(request.app.state.clock)
        request.app.state.key_cache = cache
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        limiter = MemoryRateLimiter()
        request.app.state.rate_limiter = limiter
    slots = getattr(request.app.state, "slots", None)
    if slots is None:
        slots = MemorySlots()
        request.app.state.slots = slots
    transport = getattr(request.app.state, "upstream_transport", None)
    if transport is not None and not isinstance(transport, httpx.AsyncBaseTransport):
        transport = None
    client = getattr(request.app.state, "upstream_client", None)
    return GatewayService(
        session,
        request.app.state.clock,
        request.app.state.settings,
        cache,
        limiter,
        slots,
        transport,
        upstream_client=client,
    )


async def _session(request: Request) -> Any:
    sessionmaker = request.app.state.sessionmaker
    if sessionmaker is None:
        raise AppError(503, "GATEWAY_DB_NOT_READY")
    return sessionmaker()


@router.get("/v1/models", response_model=None)
async def models(request: Request) -> JSONResponse:
    try:
        async with await _session(request) as session:
            try:
                data = await _service(request, session).list_models(_bearer(request))
                await session.commit()
            except AppError as exc:
                await session.commit()
                return _openai(exc)
        return JSONResponse(data)
    except AppError as exc:
        return _openai(exc)


@router.post("/v1/chat/completions", response_model=None)
async def chat(request: Request) -> JSONResponse | StreamingResponse:
    return await _forward(request, require_embeddings=False)


@router.post("/v1/embeddings", response_model=None)
async def embeddings(request: Request) -> JSONResponse | StreamingResponse:
    return await _forward(request, require_embeddings=True)


def _closed(request: Request) -> JSONResponse:
    _ = request
    return _openai(AppError(501, "ENDPOINT_NOT_OPEN"))


@router.post("/v1/images/generations", response_model=None)
async def images_generations(request: Request) -> JSONResponse:
    return _closed(request)


@router.post("/v1/audio/transcriptions", response_model=None)
async def audio_transcriptions(request: Request) -> JSONResponse:
    return _closed(request)


@router.post("/v1/audio/speech", response_model=None)
async def audio_speech(request: Request) -> JSONResponse:
    return _closed(request)


@router.get("/v1/files", response_model=None)
async def files_list(request: Request) -> JSONResponse:
    return _closed(request)


@router.post("/v1/files", response_model=None)
async def files_create(request: Request) -> JSONResponse:
    return _closed(request)


@router.get("/v1/batches", response_model=None)
async def batches_list(request: Request) -> JSONResponse:
    return _closed(request)


@router.post("/v1/batches", response_model=None)
async def batches_create(request: Request) -> JSONResponse:
    return _closed(request)


async def _forward(request: Request, *, require_embeddings: bool) -> JSONResponse | StreamingResponse:
    if closed_path(request.url.path):
        return _openai(AppError(501, "ENDPOINT_NOT_OPEN"))
    try:
        body = await request.json()
    except ValueError:
        return _openai(AppError(400, "BODY_MUST_BE_JSON"))
    if not isinstance(body, dict):
        return _openai(AppError(400, "BODY_MUST_BE_JSON_OBJECT"))
    ip = client_ip(request) or None
    request_id = str(getattr(request.state, "request_id", "unknown"))
    prepared = None
    try:
        async with await _session(request) as session:
            try:
                service = _service(request, session)
                prepared = await service.prepare(
                    raw_key=_bearer(request),
                    body=body,
                    request_id=request_id,
                    ip=ip,
                    require_embeddings=require_embeddings,
                )
                if not prepared.stream:
                    payload = await (
                        service.embeddings(prepared) if require_embeddings else service.complete(prepared)
                    )
                    await session.commit()
                    return JSONResponse(payload)
                await session.commit()
            except AppError as exc:
                await session.commit()
                return _openai(exc)
    except AppError as exc:
        return _openai(exc)
    if prepared is None:
        return _openai(AppError(500, "INTERNAL"))
    sessionmaker = request.app.state.sessionmaker

    async def generate() -> AsyncIterator[str]:
        # 流式期间不再持有请求会话：结算由 service.stream 内部用 sessionmaker 另开短会话。
        service = _service(request, None)
        async for line in service.stream(prepared, request.is_disconnected, sessionmaker):
            yield line

    return StreamingResponse(generate(), media_type="text/event-stream")
