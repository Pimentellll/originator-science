"""Serve the MIRAGE frontend and API together on one port."""

from __future__ import annotations

import argparse
import os
import secrets
from collections.abc import Sequence
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

if __package__:
    from . import serve_api
else:
    import serve_api


class _EvaluationTokenInjector:
    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self.token is not None:
            path = scope.get("path", "")
            if path.startswith("/api/"):
                path = path[4:]
            if path == "/benchmarks" or path.startswith("/benchmarks/"):
                headers = [
                    (name, value)
                    for name, value in scope.get("headers", [])
                    if name.lower() != b"x-mirage-eval-token"
                ]
                headers.append(
                    (b"x-mirage-eval-token", self.token.encode("latin-1"))
                )
                scope = {**scope, "headers": headers}
        await self.app(scope, receive, send)


def create_web_app(
    api_app: ASGIApp, dist_dir: Path, token: str | None
) -> Starlette:
    return Starlette(
        routes=[
            Mount(
                "/api",
                app=_EvaluationTokenInjector(api_app, token),
                name="api",
            ),
            Mount(
                "/",
                app=StaticFiles(directory=dist_dir, html=True),
                name="web",
            ),
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = serve_api.build_parser(
        host_default="0.0.0.0",
        port_default=int(os.environ.get("PORT") or 8000),
        records_default=Path("/tmp/mirage-records"),
    )
    parser.description = "Serve the MIRAGE frontend and API on one port."
    parser.set_defaults(cors_origin=[])
    parser.add_argument("--dist", type=Path, default=Path("frontend/dist"))
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    token = os.environ.get("MIRAGE_EVAL_TOKEN") or secrets.token_urlsafe(18)
    api_app = serve_api.build_app(args, token)
    app = create_web_app(api_app, args.dist, token)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
