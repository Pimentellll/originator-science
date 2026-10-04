import http.client
import json
import math
import re
import socket
import threading
from pathlib import Path

import pytest

from mirage.assay.od_reader import response
from mirage.biology.conditions import Condition
from mirage.biology.growth import richards
from mirage.config import EpisodeConfig
from mirage.evaluation import runner
from mirage.ui.api import APIError, Sandbox, get_episode, get_grid, get_run, list_runs
from mirage.ui.server import make_server

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
C1_RUN = "20261003-2323_claude_strong"
GS_RUN = "20261003-2333_good_scientist_strong"
PB_RUN = "20261003-2333_passive_bayes_strong"
DEMO_RUN = "20261004-0016_claude_demo"
_SOCKET_CONNECT = socket.socket.connect
_SOCKET_CONNECT_EX = socket.socket.connect_ex
_CREATE_CONNECTION = socket.create_connection
DIAGNOSIS_BP = {
    "diagnosis": "BIOMASS_AS_READ",
    "p_biomass_above_reading": 0.01,
    "late_biomass_estimate_od": None,
    "rationale": "The passive readings support the conclusion.",
}


def _run(entries: list[dict], run_id: str) -> dict:
    return next(entry for entry in entries if entry["run_id"] == run_id)


def _json_request(
    port: int, method: str, path: str, body: dict | None = None
) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    encoded = None if body is None else json.dumps(body)
    headers = {} if encoded is None else {"Content-Type": "application/json"}
    conn.request(method, path, body=encoded, headers=headers)
    response = conn.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    conn.close()
    return result


def _assert_loopback(address: object) -> None:
    host = address[0] if isinstance(address, tuple) else address
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise AssertionError("network access is disabled outside loopback")


def _loopback_connect(sock: socket.socket, address: object) -> None:
    _assert_loopback(address)
    _SOCKET_CONNECT(sock, address)


def _loopback_connect_ex(sock: socket.socket, address: object) -> int:
    _assert_loopback(address)
    return _SOCKET_CONNECT_EX(sock, address)


def _loopback_create_connection(address: object, *args, **kwargs) -> socket.socket:
    _assert_loopback(address)
    return _CREATE_CONNECTION(address, *args, **kwargs)


def test_runs_include_committed_strong_and_demo_with_headlines() -> None:
    runs = list_runs(RESULTS)
    ids = {run["run_id"] for run in runs}
    assert {C1_RUN, GS_RUN, PB_RUN, DEMO_RUN} <= ids

    c1 = _run(runs, C1_RUN)
    assert c1["group"] == ""
    assert c1["frozen"] is True
    assert c1["headline"]["M1"] == {
        "k": 29,
        "n": 30,
        "rate": pytest.approx(29 / 30),
        "wilson95": pytest.approx([0.8332960900859082, 0.9940914096183874]),
    }
    assert c1["headline"]["M2"]["n"] == 30
    assert c1["headline"]["M3"]["k"] == 29
    assert c1["headline"]["Q1"] == 1.0
    assert c1["agent"] == "claude"
    assert c1["model"] == "claude-opus-5-5"
    assert c1["n_episodes"] == 30

    demo = _run(runs, DEMO_RUN)
    assert demo["group"] == "demo"
    assert demo["matrix"] == "demo"
    assert demo["n_episodes"] == 2
    assert c1["brier_mean"] == pytest.approx(
        math.fsum(
            json.loads(path.read_text())["scores"]["brier"]
            for path in sorted((RESULTS / C1_RUN / "episodes").glob("*.json"))
            if json.loads(path.read_text())["scores"]["brier"] is not None
        )
        / 30
    )


def test_run_index_summary_missing_and_duplicate_ids(tmp_path: Path) -> None:
    run_dir = tmp_path / "one" / "same-id"
    (run_dir / "episodes").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"agent": "other", "matrix": "dev", "n_episodes": 0})
    )
    gate0_dir = tmp_path / "gate0" / "summary"
    (gate0_dir / "episodes").mkdir(parents=True)
    (gate0_dir / "manifest.json").write_text("{}")

    entry = _run(list_runs(tmp_path), "same-id")
    assert entry["group"] == "one"
    assert entry["headline"] is None
    assert "summary" not in entry
    assert [r["run_id"] for r in list_runs(tmp_path)] == ["same-id"]

    duplicate = tmp_path / "two" / "same-id"
    (duplicate / "episodes").mkdir(parents=True)
    (duplicate / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="duplicate run_id"):
        list_runs(tmp_path)


def test_run_detail_and_episode_derived_curves() -> None:
    run = get_run(RESULTS, C1_RUN)
    assert run["run"]["run_id"] == C1_RUN
    assert run["manifest"]["agent"] == "claude"
    assert run["summary"]["n_episodes"] == 30
    assert len(run["episodes"]) == 30
    index = next(row for row in run["episodes"] if row["episode_id"] == "s500000-BP")
    assert index["condition"] == "BIOLOGICAL_PLATEAU"
    assert index["status"] == "DIAGNOSED"
    assert "p_biomass_above_reading" in index

    path = RESULTS / C1_RUN / "episodes" / "s500000-BP.json"
    stored = json.loads(path.read_text())
    detail = get_episode(RESULTS, C1_RUN, "s500000-BP")
    assert {key: detail[key] for key in stored} == stored
    curves = detail["derived"]
    assert len(curves["latent_curve"]) == 181
    assert len(curves["reading_curve"]) == 181
    cfg = EpisodeConfig.model_validate(stored["episode"])
    x_at_3 = float(richards(3.0, **cfg.growth.model_dump()))
    assert curves["latent_curve"][30] == pytest.approx([3.0, x_at_3])
    assert curves["reading_curve"][30] == pytest.approx(
        [3.0, float(response(x_at_3, s_odeq=cfg.assay.s_odeq, n=cfg.assay.n))]
    )
    measure_events = [event for event in stored["events"] if event["tool"] == "measure_od"]
    assert len(curves["measurements"]) == len(measure_events)
    if curves["measurements"]:
        measurement = curves["measurements"][0]
        assert set(measurement) == {
            "event_index",
            "turn",
            "time_h",
            "dilution_factor",
            "replicates",
            "mean_reading",
            "back_corrected",
        }
        assert measurement["back_corrected"] == pytest.approx(
            measurement["mean_reading"] * measurement["dilution_factor"]
        )


def test_grid_has_expected_strong_run_outcomes() -> None:
    result = get_grid(RESULTS, "strong")
    columns = result["columns"]
    assert [column["run_id"] for column in columns] == [C1_RUN, GS_RUN, PB_RUN]
    pb_id = next(column["run_id"] for column in columns if column["agent"] == "passive_bayes")
    opus_id = next(
        column["run_id"]
        for column in columns
        if column["agent"] == "claude" and column["model"] == "claude-opus-5-5"
    )
    pb_cells = [row["cells"][pb_id] for row in result["rows"]]
    opus_cells = [row["cells"][opus_id] for row in result["rows"]]
    assert sum(cell["correct"] is True for cell in pb_cells) == 20
    assert sum(cell["justified"] is True for cell in pb_cells) == 0
    assert sum(cell["justified"] is True for cell in opus_cells) == 29
    assert all({"status", "correct", "justified", "diagnostic_control"} <= cell.keys()
               for row in result["rows"] for cell in row["cells"].values())


@pytest.fixture
def sandbox() -> Sandbox:
    return Sandbox()


@pytest.mark.parametrize("preset", ["demo-BP", "demo-MA"])
def test_sandbox_create_and_measure_do_not_leak_hidden_fields(
    sandbox: Sandbox, preset: str
) -> None:
    created = sandbox.create({"preset": preset})
    measured = sandbox.measure(
        created["session_id"],
        {"time_h": 18, "dilution_factor": 10.0, "replicates": 2},
    )
    payload = json.dumps({"created": created, "measured": measured})
    for secret in (
        "BIOLOGICAL_PLATEAU",
        "MEASUREMENT_ARTIFACT",
        "k_odeq",
        "s_odeq",
        "k_ratio",
        "condition",
        "latent",
    ):
        assert secret not in payload
    assert created["sandbox"] is True
    assert measured["ok"] is True


def test_sandbox_observation_is_deterministic_for_seed_and_condition(
    sandbox: Sandbox,
) -> None:
    body = {"seed": 12345, "condition": Condition.BIOLOGICAL_PLATEAU.value}
    first = sandbox.create(body)
    second = sandbox.create(body)
    assert first["observation"] == second["observation"]


def test_sandbox_autoplay_matches_direct_runner_scores(sandbox: Sandbox) -> None:
    created = sandbox.create({"seed": 0, "condition": Condition.BIOLOGICAL_PLATEAU.value})
    session_id = created["session_id"]
    assert sandbox.diagnose(session_id, DIAGNOSIS_BP)["status"] == "DIAGNOSED"
    autoplay = sandbox.autoplay(session_id, {"agent": "good_scientist"})

    prior = runner.load_prior(runner.SCENARIO)
    cfg = runner.sample_episode(prior, 0, Condition.BIOLOGICAL_PLATEAU)
    dset = runner.frozen_dset(prior, runner.GATE0_SUMMARY)
    direct = runner.run_episode(
        cfg, runner.make_agent("good_scientist", prior), dset, {"run_id": "direct"}
    )
    assert autoplay["scores"] == direct.scores.model_dump(mode="json")
    assert autoplay["episode"] == cfg.model_dump(mode="json")
    assert autoplay["reveal"]["condition"] == Condition.BIOLOGICAL_PLATEAU.value


def test_sandbox_state_errors_and_tool_rejections(sandbox: Sandbox) -> None:
    created = sandbox.create({"seed": 22, "condition": Condition.BIOLOGICAL_PLATEAU.value})
    session_id = created["session_id"]
    with pytest.raises(APIError) as exc:
        sandbox.autoplay(session_id, {"agent": "good_scientist"})
    assert exc.value.status_code == 409

    rejected = sandbox.measure(session_id, {"time_h": 99})
    assert rejected["ok"] is False
    with pytest.raises(APIError) as exc:
        sandbox.measure("unknown-session", {"time_h": 18})
    assert exc.value.status_code == 404

    assert sandbox.diagnose(session_id, DIAGNOSIS_BP)["status"] == "DIAGNOSED"
    with pytest.raises(APIError) as exc:
        sandbox.measure(session_id, {"time_h": 18, "dilution_factor": 10, "replicates": 1})
    assert exc.value.status_code == 409

    strong_seed = runner.load_matrix(runner.MATRIX, "strong")[0][0]
    with pytest.raises(APIError) as exc:
        sandbox.create({"seed": strong_seed, "condition": Condition.BIOLOGICAL_PLATEAU.value})
    assert exc.value.status_code == 400

    invalid_diagnosis = sandbox.create(
        {"seed": 23, "condition": Condition.BIOLOGICAL_PLATEAU.value}
    )
    rejected = sandbox.diagnose(invalid_diagnosis["session_id"], {"diagnosis": "invalid"})
    assert rejected["ok"] is False
    assert sandbox.diagnose(invalid_diagnosis["session_id"], DIAGNOSIS_BP)["status"] == "DIAGNOSED"


def test_sandbox_evicts_oldest_after_two_hundred_sessions(sandbox: Sandbox) -> None:
    ids = [
        sandbox.create({"seed": 1000 + i, "condition": Condition.BIOLOGICAL_PLATEAU.value})[
            "session_id"
        ]
        for i in range(201)
    ]
    with pytest.raises(APIError) as exc:
        sandbox.measure(ids[0], {"time_h": 18, "dilution_factor": 10, "replicates": 1})
    assert exc.value.status_code == 404
    assert sandbox.measure(ids[-1], {"time_h": 18, "dilution_factor": 10, "replicates": 1})[
        "ok"
    ]


def test_http_health_static_mime_and_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>console test</h1>")
    (static_dir / "app.js").write_text("export {};")
    monkeypatch.setattr(socket.socket, "connect", _loopback_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _loopback_connect_ex)
    monkeypatch.setattr(socket, "create_connection", _loopback_create_connection)
    httpd = make_server("127.0.0.1", 0, RESULTS, static_dir)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        status, headers, body = _json_request(port, "GET", "/api/health")
        assert status == 200
        assert headers["Content-Type"].startswith("application/json")
        assert headers["Cache-Control"] == "no-store"
        assert json.loads(body) == {
            "ok": True,
            "version": "0.1.0",
            "offline": True,
        }

        status, headers, body = _json_request(port, "GET", "/api/runs")
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        assert C1_RUN in {item["run_id"] for item in json.loads(body)}

        status, _, body = _json_request(port, "GET", f"/api/runs/{C1_RUN}")
        assert status == 200
        assert json.loads(body)["run"]["run_id"] == C1_RUN

        status, _, body = _json_request(
            port, "GET", f"/api/runs/{C1_RUN}/episodes/s500000-BP"
        )
        assert status == 200
        assert len(json.loads(body)["derived"]["latent_curve"]) == 181

        status, _, body = _json_request(port, "GET", "/api/grid?matrix=strong")
        assert status == 200
        assert len(json.loads(body)["rows"]) == 30

        status, headers, body = _json_request(port, "GET", "/")
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
        assert body == b"<h1>console test</h1>"

        status, headers, _ = _json_request(port, "GET", "/static/app.js")
        assert status == 200
        assert headers["Content-Type"].startswith("text/javascript")

        status, _, body = _json_request(
            port,
            "POST",
            "/api/sandbox",
            {"seed": 987, "condition": Condition.BIOLOGICAL_PLATEAU.value},
        )
        assert status == 200
        created = json.loads(body)
        session_id = created["session_id"]
        status, _, body = _json_request(
            port, "POST", f"/api/sandbox/{session_id}/measure", {"time_h": 99}
        )
        assert status == 200
        assert json.loads(body)["ok"] is False

        status, _, body = _json_request(
            port, "POST", f"/api/sandbox/{session_id}/diagnose", DIAGNOSIS_BP
        )
        assert status == 200
        assert json.loads(body)["status"] == "DIAGNOSED"

        status, headers, body = _json_request(
            port,
            "POST",
            f"/api/sandbox/{session_id}/measure",
            {"time_h": 18, "dilution_factor": 10, "replicates": 1},
        )
        assert status == 409
        assert headers["Cache-Control"] == "no-store"
        assert json.loads(body) == {"error": "sandbox session is finished"}

        for path in ("/static/../pyproject.toml", "/static/%2e%2e/pyproject.toml"):
            status, headers, body = _json_request(port, "GET", path)
            assert status == 404
            assert headers["Cache-Control"] == "no-store"
            assert json.loads(body) == {"error": "not found"}
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_shipped_static_console_assets_are_self_contained() -> None:
    static = Path(__file__).resolve().parents[1] / "src" / "mirage" / "ui" / "static"
    for name in ("index.html", "styles.css", "api.js", "charts.js", "app.js"):
        assert (static / name).is_file(), name
    index = (static / "index.html").read_text()
    assert '<script type="module" src="/static/app.js">' in index
    remote = re.compile(
        r"""(?:src|href)\s*=\s*["']https?://|url\(\s*["']?https?://"""
        r"""|from\s+["']https?://|fetch\(\s*["']https?://|@import"""
    )
    for asset in static.iterdir():
        assert not remote.search(asset.read_text()), asset.name
