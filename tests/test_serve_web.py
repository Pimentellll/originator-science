import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


serve_api = _load_script("serve_api")
serve_web = _load_script("serve_web")


def test_web_app_serves_frontend_and_injects_benchmark_token(tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<main>MIRAGE</main>")
    token = "server-token"
    args = serve_api.parse_args(
        [
            "--records",
            str(tmp_path / "records"),
            "--growth-results",
            str(tmp_path / "growth-results"),
        ]
    )
    api_app = serve_api.build_app(args, token)
    client = TestClient(serve_web.create_web_app(api_app, dist_dir, token))

    home = client.get("/")
    assert home.status_code == 200
    assert home.text == "<main>MIRAGE</main>"
    assert client.get("/api/health").status_code == 200

    direct = TestClient(api_app)
    assert direct.get("/benchmarks/growth/runs").status_code == 403
    assert client.get("/api/benchmarks/growth/runs").status_code == 200
    assert (
        client.get(
            "/api/benchmarks/growth/runs",
            headers={"X-Mirage-Eval-Token": "client-supplied-wrong-token"},
        ).status_code
        == 200
    )


def test_mounted_api_serves_growth_grid(tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<main>MIRAGE</main>")
    results = Path(__file__).resolve().parents[1] / "experiments" / "results"
    args = serve_api.parse_args(["--records", str(tmp_path / "records"), "--growth-results", str(results)])
    client = TestClient(serve_web.create_web_app(serve_api.build_app(args, "t"), dist_dir, "t"))
    grid = client.get("/api/benchmarks/growth/grid?matrix=strong")
    assert grid.status_code == 200, grid.text
    assert grid.json()["columns"]
