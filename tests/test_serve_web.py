from pathlib import Path

from fastapi.testclient import TestClient

from scripts.serve_api import build_app, parse_args
from scripts.serve_web import create_web_app


def test_web_app_serves_frontend_and_injects_benchmark_token(tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<main>MIRAGE</main>")
    token = "server-token"
    args = parse_args(
        [
            "--records",
            str(tmp_path / "records"),
            "--growth-results",
            str(tmp_path / "growth-results"),
        ]
    )
    api_app = build_app(args, token)
    client = TestClient(create_web_app(api_app, dist_dir, token))

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
    args = parse_args(["--records", str(tmp_path / "records"), "--growth-results", str(results)])
    client = TestClient(create_web_app(build_app(args, "t"), dist_dir, "t"))
    grid = client.get("/api/benchmarks/growth/grid?matrix=strong")
    assert grid.status_code == 200, grid.text
    assert grid.json()["columns"]
