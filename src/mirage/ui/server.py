"""Local JSON API and static-file server for the MIRAGE-Bio console."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from mirage.ui import api

DEFAULT_STATIC_DIR = Path(__file__).parent / "static"


def make_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    results_root: str | Path = Path("experiments/results"),
    static_dir: str | Path | None = None,
) -> ThreadingHTTPServer:
    """Create a threaded local server; callers may run it in a test thread."""
    results_root = Path(results_root)
    static_root = Path(static_dir) if static_dir is not None else DEFAULT_STATIC_DIR
    sandbox = api.Sandbox()

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict[str, Any] | list[Any]) -> None:
            data = json.dumps(
                payload, sort_keys=True, ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_file(self, path: Path) -> None:
            data = path.read_bytes()
            content_type = (
                "text/javascript"
                if path.suffix.lower() == ".js"
                else mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            if content_type.startswith("text/"):
                content_type += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, err: Exception) -> None:
            if isinstance(err, api.APIError):
                self._send_json(err.status_code, {"error": str(err)})
            elif isinstance(err, (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError)):
                self._send_json(400, {"error": str(err) or "bad request"})
            elif isinstance(err, (FileNotFoundError, KeyError)):
                self._send_json(404, {"error": "not found"})
            else:
                self._send_json(500, {"error": "internal server error"})

        def _dispatch(self, operation) -> None:
            try:
                operation()
            except Exception as err:
                self._error(err)

        def _read_json(self) -> dict[str, Any]:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError as err:
                raise api.APIError(400, "invalid Content-Length") from err
            if content_length < 0:
                raise api.APIError(400, "invalid Content-Length")
            try:
                payload = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, UnicodeDecodeError) as err:
                raise api.APIError(400, "request body must be valid JSON") from err
            if not isinstance(payload, dict):
                raise api.APIError(400, "request body must be a JSON object")
            return payload

        def _static_file(self, request_path: str) -> Path:
            root = static_root.resolve()
            if request_path == "/":
                candidate = (root / "index.html").resolve()
            else:
                relative = unquote(request_path[len("/static/") :])
                candidate = (root / relative).resolve()
            if not candidate.is_relative_to(root) or not candidate.is_file():
                raise api.APIError(404, "not found")
            return candidate

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)

            def route() -> None:
                if path == "/api/health":
                    self._send_json(200, api.health())
                elif path == "/api/runs":
                    self._send_json(200, api.list_runs(results_root))
                elif path == "/api/grid":
                    matrices = parse_qs(parsed.query, keep_blank_values=True).get("matrix")
                    if not matrices or not matrices[0]:
                        raise api.APIError(400, "matrix query parameter is required")
                    self._send_json(200, api.get_grid(results_root, matrices[0]))
                elif path.startswith("/api/runs/"):
                    parts = path.split("/")
                    if len(parts) == 4:
                        self._send_json(200, api.get_run(results_root, parts[3]))
                    elif len(parts) == 6 and parts[4] == "episodes":
                        self._send_json(
                            200, api.get_episode(results_root, parts[3], parts[5])
                        )
                    else:
                        raise api.APIError(404, "not found")
                elif path == "/" or path.startswith("/static/"):
                    self._send_file(self._static_file(path))
                else:
                    raise api.APIError(404, "not found")

            self._dispatch(route)

        def do_POST(self) -> None:
            path = unquote(urlsplit(self.path).path)

            def route() -> None:
                if path == "/api/sandbox":
                    self._send_json(200, sandbox.create(self._read_json()))
                    return
                parts = path.split("/")
                if len(parts) != 5 or parts[1:3] != ["api", "sandbox"]:
                    raise api.APIError(404, "not found")
                session_id, action = parts[3], parts[4]
                body = self._read_json()
                if action == "measure":
                    result = sandbox.measure(session_id, body)
                elif action == "diagnose":
                    result = sandbox.diagnose(session_id, body)
                elif action == "autoplay":
                    result = sandbox.autoplay(session_id, body)
                else:
                    raise api.APIError(404, "not found")
                self._send_json(200, result)

            self._dispatch(route)

        def do_PUT(self) -> None:
            self._send_json(404, {"error": "not found"})

        def do_DELETE(self) -> None:
            self._send_json(404, {"error": "not found"})

    class ConsoleHTTPServer(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    return ConsoleHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mirage-ui")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--results", type=Path, default=Path("experiments/results"))
    args = parser.parse_args(argv)
    httpd = make_server(args.host, args.port, args.results)
    print(f"Serving console at http://{args.host}:{httpd.server_address[1]}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
