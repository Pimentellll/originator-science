"""Growth-benchmark API routes, separated by their trust boundary."""

from __future__ import annotations

import hmac
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from mirage.ui import api


def create_growth_router(
    results_root: Path, *, aggregate_token: str | None
) -> APIRouter:
    router = APIRouter()
    sandbox = api.Sandbox()

    def _error(error: api.APIError) -> JSONResponse:
        return JSONResponse(
            {"detail": str(error)}, status_code=error.status_code
        )

    def _authorize(token: str | None) -> None:
        if not aggregate_token:
            raise api.APIError(404, "aggregate results are not enabled")
        if token is None or not hmac.compare_digest(
            token.encode(), aggregate_token.encode()
        ):
            raise api.APIError(403, "not authorised")

    def _gated(token: str | None, call: Callable[[], Any]) -> Any:
        try:
            _authorize(token)
            return call()
        except api.APIError as error:
            return _error(error)

    async def _json_object(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise api.APIError(400, "request body must be a JSON object") from error
        if not isinstance(body, dict):
            raise api.APIError(400, "request body must be a JSON object")
        return body

    async def _public_post(
        request: Request, operation: Callable[[dict[str, Any]], Any]
    ) -> Any:
        try:
            body = await _json_object(request)
            return await run_in_threadpool(operation, body)
        except api.APIError as error:
            return _error(error)

    async def _gated_post(
        token: str | None,
        request: Request,
        operation: Callable[[dict[str, Any]], Any],
    ) -> Any:
        try:
            _authorize(token)
            body = await _json_object(request)
            return await run_in_threadpool(operation, body)
        except api.APIError as error:
            return _error(error)

    @router.get("/benchmarks/growth/runs")
    def list_growth_runs(
        x_mirage_eval_token: str | None = Header(default=None),
    ) -> Any:
        return _gated(
            x_mirage_eval_token, lambda: api.list_runs(results_root)
        )

    @router.get("/benchmarks/growth/runs/{run_id}")
    def read_growth_run(
        run_id: str, x_mirage_eval_token: str | None = Header(default=None)
    ) -> Any:
        return _gated(
            x_mirage_eval_token, lambda: api.get_run(results_root, run_id)
        )

    @router.get("/benchmarks/growth/runs/{run_id}/episodes/{episode_id}")
    def read_growth_episode(
        run_id: str,
        episode_id: str,
        x_mirage_eval_token: str | None = Header(default=None),
    ) -> Any:
        return _gated(
            x_mirage_eval_token,
            lambda: api.get_episode(results_root, run_id, episode_id),
        )

    @router.get("/benchmarks/growth/grid")
    def read_growth_grid(
        matrix: str | None = None,
        x_mirage_eval_token: str | None = Header(default=None),
    ) -> Any:
        def get_grid() -> Any:
            if not matrix:
                raise api.APIError(400, "matrix is required")
            return api.get_grid(results_root, matrix)

        return _gated(x_mirage_eval_token, get_grid)

    @router.get("/benchmarks/growth/sandbox/{session_id}/verdict")
    def read_sandbox_verdict(
        session_id: str, x_mirage_eval_token: str | None = Header(default=None)
    ) -> Any:
        return _gated(
            x_mirage_eval_token, lambda: sandbox.verdict(session_id)
        )

    @router.post("/benchmarks/growth/sandbox/{session_id}/autoplay")
    async def autoplay_sandbox(
        session_id: str,
        request: Request,
        x_mirage_eval_token: str | None = Header(default=None),
    ) -> Any:
        return await _gated_post(
            x_mirage_eval_token,
            request,
            lambda body: sandbox.autoplay(session_id, body),
        )

    @router.post("/growth/sandbox")
    async def create_sandbox(request: Request) -> Any:
        return await _public_post(request, sandbox.create)

    @router.post("/growth/sandbox/{session_id}/measure")
    async def measure_sandbox(session_id: str, request: Request) -> Any:
        return await _public_post(
            request, lambda body: sandbox.measure(session_id, body)
        )

    @router.post("/growth/sandbox/{session_id}/diagnose")
    async def diagnose_sandbox(session_id: str, request: Request) -> Any:
        return await _public_post(
            request, lambda body: sandbox.submit(session_id, body)
        )

    return router
