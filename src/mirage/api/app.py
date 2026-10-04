"""Public FastAPI application (FRONTEND_API_CONTRACT.md).

fastapi/uvicorn/httpx are shared dependencies requested from the integration owner; they
are imported only here so the rest of MIRAGE works without them.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from mirage.api.dto import (
    ActionDTO,
    ActionRequest,
    HealthDTO,
    PublicStateDTO,
    RecommendationDTO,
    ReplayDTO,
    ResetRequest,
    StepDTO,
)
from mirage.api.growth import create_growth_router
from mirage.api.service import EpisodeService, Forbidden, NotFound, ServiceError
from mirage.evaluation.campaign.aggregate import BenchmarkSummary, EvaluationStore
from mirage.provenance import find_privileged_fields
from mirage.provenance.store import safe_id

API_VERSION = "mirage.api/1"
TOKEN_HEADER = "X-Mirage-Eval-Token"
_BENCHMARK_PREFIX = "/benchmarks"


def create_app(
    service: EpisodeService,
    *,
    evaluation_store: EvaluationStore | None = None,
    aggregate_token: str | None = None,
    cors_origins: Sequence[str] = (),
    growth_results_root: Path | None = None,
) -> FastAPI:
    """Build the API. Aggregate benchmark results are served only when both an evaluation
    store and an access token are configured and the caller presents that token."""
    app = FastAPI(title="MIRAGE public API", version=API_VERSION)
    if cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins), allow_methods=["GET", "POST"], allow_headers=["*"])
    if growth_results_root is not None:
        app.include_router(
            create_growth_router(
                growth_results_root, aggregate_token=aggregate_token
            )
        )

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse({"detail": exc.public_message}, status_code=exc.status)

    @app.middleware("http")
    async def _leak_guard(request: Request, call_next):
        """Defence in depth: refuse to send any non-aggregate JSON body that carries a
        privileged-looking key, even if a DTO bug let one through."""
        response = await call_next(request)
        if request.url.path.startswith(_BENCHMARK_PREFIX):
            return response
        if "application/json" not in response.headers.get("content-type", ""):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            leaked = find_privileged_fields(json.loads(body))
        except ValueError:
            leaked = []
        if leaked:
            return JSONResponse({"detail": "response blocked by trust boundary"}, status_code=500)
        return Response(content=body, status_code=response.status_code, headers=dict(response.headers))

    @app.get("/health", response_model=HealthDTO)
    def health() -> HealthDTO:
        return HealthDTO(status="ok", version=API_VERSION)

    @app.post("/episodes", response_model=PublicStateDTO, status_code=201)
    def reset_episode(body: ResetRequest | None = None) -> PublicStateDTO:
        body = body or ResetRequest()
        return service.create(body.seed, body.policy_name)

    @app.get("/episodes/{episode_id}", response_model=PublicStateDTO)
    def read_state(episode_id: str) -> PublicStateDTO:
        return service.state(_checked(episode_id))

    @app.get("/episodes/{episode_id}/actions", response_model=tuple[ActionDTO, ...])
    def read_actions(episode_id: str):
        return service.available_actions(_checked(episode_id))

    @app.post("/episodes/{episode_id}/actions", response_model=StepDTO)
    def take_action(episode_id: str, body: ActionRequest) -> StepDTO:
        return service.act(_checked(episode_id), body)

    @app.get("/episodes/{episode_id}/recommendation", response_model=RecommendationDTO)
    def read_recommendation(episode_id: str) -> RecommendationDTO:
        return service.recommend(_checked(episode_id))

    @app.get("/episodes/{episode_id}/replay", response_model=ReplayDTO)
    def read_replay(episode_id: str) -> ReplayDTO:
        return service.replay(_checked(episode_id))

    def _authorised(token: str | None) -> None:
        if evaluation_store is None or not aggregate_token:
            raise NotFound("aggregate results are not enabled")
        if token is None or not hmac.compare_digest(token.encode(), aggregate_token.encode()):
            raise Forbidden("not authorised")

    @app.get("/benchmarks", response_model=tuple[str, ...])
    def list_benchmarks(x_mirage_eval_token: str | None = Header(default=None)):
        _authorised(x_mirage_eval_token)
        assert evaluation_store is not None
        return evaluation_store.list_summaries()

    @app.get("/benchmarks/{benchmark_id}", response_model=BenchmarkSummary)
    def read_benchmark(benchmark_id: str, x_mirage_eval_token: str | None = Header(default=None)):
        _authorised(x_mirage_eval_token)
        assert evaluation_store is not None
        try:
            return evaluation_store.load_summary(_checked(benchmark_id))
        except FileNotFoundError:
            raise NotFound("benchmark not found") from None

    return app


def _checked(identifier: str) -> str:
    try:
        return safe_id(identifier)
    except ValueError:
        raise NotFound("not found") from None
