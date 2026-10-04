"""./mirage launcher: platform/ports/pid safety, grouped-test invariants, CLI behaviour from any
directory, and an end-to-end demo acceptance test (real API + Vite, SIGINT, no leftovers).

The launcher is standard-library-only and lives in scripts/ (not a package), so it is imported by path.
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import mirage_env as E  # noqa: E402
import mirage_cli as C  # noqa: E402
import run_tests as RT  # noqa: E402
import supervisor as S  # noqa: E402
from benchmark_command import development_benchmark_argv  # noqa: E402
from mirage.environments.binder import BinderWorldMode  # noqa: E402

MIRAGE = ROOT / "mirage"


def cli(*args, cwd=None, timeout=120):
    return subprocess.run([str(MIRAGE), *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


# ------------------------------------------------------------------ pure helpers
@pytest.mark.parametrize("version,ok", [("20.19.0", True), ("20.18.9", False), ("22.12.0", True), ("22.11.0", False), ("24.1.0", True), ("18.20.0", False)])
def test_node_version_rule_matches_vite(version, ok):
    assert E.node_ok(version) is ok


def test_find_free_port_skips_a_busy_port_without_touching_it():
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    busy = holder.getsockname()[1]
    try:
        assert not E.port_free(busy)
        chosen = E.find_free_port(busy)
        assert chosen != busy and E.port_free(chosen)
        assert holder.fileno() != -1  # still listening: nothing was killed or closed
    finally:
        holder.close()


def test_pick_port_moves_on_when_an_unrelated_program_holds_the_port(capsys):
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    busy = holder.getsockname()[1]
    try:
        chosen = S.pick_port(busy, "api", "the API", set())
        assert chosen != busy
        assert "left untouched" in capsys.readouterr().out
    finally:
        holder.close()


def test_pidfile_for_a_recycled_pid_is_never_trusted(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "PIDS", tmp_path)
    E.write_pidfile("api", os.getpid(), port=1)  # alive, but this is pytest, not serve_api.py
    assert E.owned_pid("api") is None


def test_pidfile_for_another_checkout_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "PIDS", tmp_path)
    E.write_pidfile("supervisor", os.getpid())
    rec = json.loads((tmp_path / "supervisor.json").read_text())
    rec["root"] = "/somewhere/else"
    (tmp_path / "supervisor.json").write_text(json.dumps(rec))
    assert E.owned_pid("supervisor") is None


def test_windows_is_refused_with_wsl_instructions():
    assert "WSL2" in E.WINDOWS_MESSAGE and "not support native Windows" in E.WINDOWS_MESSAGE


def test_demo_scenarios_match_the_backend_world_modes():
    assert set(S.SCENARIOS) == {m.value for m in BinderWorldMode}


def test_demo_defaults_are_semantics_v2_rescue_planner_seed_9():
    ns = S.parse([])
    assert (ns.version, ns.policy, ns.seed, ns.scenario) == ("SEMANTICS_V2", "rescue_planner", 9, "COMPOUND_FAILURE")
    assert S.parse(["--scenario-version", "baseline_v1"]).version == "BASELINE_V1"  # V1 stays selectable


def test_development_benchmark_starts_when_summaries_are_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(E, "LOCAL", tmp_path)
    captured = {}
    process = object()

    def popen(argv, **kwargs):
        captured.update(argv=argv, kwargs=kwargs)
        return process

    monkeypatch.setattr(S.subprocess, "Popen", popen)
    assert S.start_development_benchmark(False) is process
    assert captured["argv"] == development_benchmark_argv()
    assert captured["kwargs"]["cwd"] == E.ROOT
    assert captured["kwargs"]["env"] == E.project_env()
    assert "generating the development-split benchmark in the background (~30 s)" in capsys.readouterr().out


def test_development_benchmark_is_skipped_when_a_summary_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "LOCAL", tmp_path)
    summaries = tmp_path / "benchmark-dev" / "binder_campaign" / "privileged" / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "binder-campaign-dev.json").write_text("{}")
    monkeypatch.setattr(S.subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("benchmark must not start"))

    assert S.start_development_benchmark(False) is None


def test_no_benchmark_flag_skips_background_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "LOCAL", tmp_path)
    args = S.parse(["--no-benchmark"])
    monkeypatch.setattr(S.subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("benchmark must not start"))

    assert args.no_benchmark
    assert S.start_development_benchmark(args.no_benchmark) is None


def test_benchmark_dev_cli_and_supervisor_use_the_same_argv(tmp_path, monkeypatch):
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(E, "ROOT", tmp_path)
    monkeypatch.setattr(E, "LOCAL", tmp_path / ".local")
    monkeypatch.setattr(E, "venv_python", lambda: python)
    cli_call = {}
    monkeypatch.setattr(C, "_stream", lambda argv, *, cwd, env: cli_call.update(argv=argv, cwd=cwd, env=env) or 0)
    assert C.cmd_benchmark_dev([]) == 0

    supervisor_call = {}
    process = object()
    monkeypatch.setattr(
        S.subprocess,
        "Popen",
        lambda argv, **kwargs: supervisor_call.update(argv=argv, kwargs=kwargs) or process,
    )
    assert S.start_development_benchmark(False) is process

    expected = [
        str(python),
        "scripts/run_binder_benchmark.py",
        "--split",
        "development",
        "--per-archetype",
        "2",
        "--out",
        str(tmp_path / ".local" / "benchmark-dev"),
        "--benchmark-id",
        "binder-campaign-dev",
    ]
    assert development_benchmark_argv() == expected
    assert cli_call["argv"] == supervisor_call["argv"] == expected
    assert cli_call["cwd"] == supervisor_call["kwargs"]["cwd"] == tmp_path
    assert cli_call["env"] == supervisor_call["kwargs"]["env"]


def test_cockpit_url_is_the_documented_default_and_carries_only_non_defaults():
    assert S.cockpit_url(S.parse([]), 5173) == "http://localhost:5173/?transport=live"
    url = S.cockpit_url(S.parse(["--seed", "4", "--scenario", "mixed", "--guided"]), 5180)
    assert url.startswith("http://localhost:5180/?transport=live") and "seed=4" in url and "scenario=MIXED" in url and "guided=1" in url


# ------------------------------------------------------------------ test wrapper invariants
def test_every_test_file_is_run_by_some_group():
    covered = set()
    for g in RT.build_groups():
        for p in g.paths:
            path = ROOT / p.split("::")[0]
            covered.update(path.rglob("test_*.py") if path.is_dir() else [path])
    every = set((ROOT / "tests").rglob("test_*.py"))
    assert every - covered == set(), "tests the grouped runner would silently skip"


def test_a_failing_gate_is_never_reported_as_pass_or_fail():
    gate = RT.Group("x", "X", [], gate=True)
    label, note = RT.classify(gate, RT.Result(failed=1))
    assert label == "NOT PASSED" and "NEW" in note
    label, note = RT.classify(RT.Group("b4a", "B", [], gate=True), RT.Result(failed=2))
    assert label == "NOT PASSED" and note.startswith("KNOWN SCIENTIFIC VALIDATION FAILURE")
    assert RT.classify(RT.Group("core", "C", []), RT.Result(failed=1))[0] == "FAIL"
    assert RT.classify(gate, RT.Result(passed=3))[0] == "PASS"


def test_known_failures_are_only_gates():
    gate_keys = {g.key for g in RT.build_groups() if g.gate}
    assert set(RT.KNOWN_GATE_FAILURES) <= gate_keys


# ------------------------------------------------------------------ CLI behaviour
def test_help_works_from_any_directory_and_through_a_symlink(tmp_path):
    assert "one-command launcher" in cli("help", cwd=tmp_path).stdout
    link = tmp_path / "m"
    link.symlink_to(MIRAGE)
    out = subprocess.run([str(link), "help"], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0 and "./mirage demo" in out.stdout


def test_unknown_command_is_an_error():
    out = cli("frobnicate")
    assert out.returncode == 2 and "unknown command" in out.stderr


def test_launcher_is_executable_and_shellcheck_clean():
    assert os.access(MIRAGE, os.X_OK)
    if shutil.which("shellcheck"):
        assert subprocess.run(["shellcheck", str(MIRAGE)], capture_output=True, text=True).returncode == 0


@pytest.mark.skipif(not E.venv_python().exists(), reason="needs .venv (run ./mirage setup)")
def test_doctor_json_is_machine_readable_and_exit_code_matches():
    out = cli("doctor", "--json", cwd="/")
    data = json.loads(out.stdout)
    assert {"ready", "checks"} <= data.keys()
    assert (out.returncode == 0) == data["ready"]
    names = {c["name"] for c in data["checks"]}
    assert {"Git", "Python", "uvicorn", "MIRAGE import", "trust-boundary smoke", "deterministic scientific smoke"} <= names
    assert all(c["status"] in {"pass", "fail", "warn", "skip"} for c in data["checks"])


@pytest.mark.skipif(not E.venv_python().exists(), reason="needs .venv (run ./mirage setup)")
def test_setup_is_idempotent():
    first = cli("setup", "--skip-frontend", timeout=600)
    second = cli("setup", "--skip-frontend", timeout=600)
    assert first.returncode == 0 and second.returncode == 0
    assert "already installed" in second.stdout


def test_clean_runtime_all_refuses_without_a_terminal_or_confirmation():
    out = subprocess.run([str(MIRAGE), "clean-runtime", "--all"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    assert out.returncode == 1 and "--yes" in out.stderr
    assert (ROOT / "mirage").exists()


# ------------------------------------------------------------------ demo acceptance
def _ready():
    # A demo the developer already has running would be reused (and must not be disturbed): skip then.
    return E.venv_python().exists() and E.frontend_deps_ready() and shutil.which("node") and not E.owned_pid("supervisor")


@pytest.mark.slow
@pytest.mark.skipif(not _ready(), reason="needs ./mirage setup (venv + frontend deps + node), and no ./mirage demo already running")
def test_demo_no_browser_serves_both_and_shuts_down_cleanly_on_sigint(tmp_path):
    api_port, web_port = E.find_free_port(18100), E.find_free_port(18200)
    proc = subprocess.Popen([str(MIRAGE), "demo", "--no-browser", "--no-benchmark", "--port", str(api_port), "--frontend-port", str(web_port), "--seed", "9"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=tmp_path)
    lines = []
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            lines.append(line)
            if "Ctrl+C to stop" in line:
                break
        text = "".join(lines)
        assert "MIRAGE is running" in text, text
        assert f"http://localhost:{web_port}/?transport=live" in text and f"http://localhost:{api_port}/docs" in text
        health = E.http_json(f"http://127.0.0.1:{api_port}/health")
        assert health and health["status"] == "ok"
        assert E.http_json(f"http://127.0.0.1:{web_port}/api/health")["status"] == "ok", "Vite proxy must follow the dynamic API port"
        assert E.http_json(f"http://127.0.0.1:{api_port}/version")["scenario_semantics_default"] == "SEMANTICS_V2"
        pids = [json.loads((E.PIDS / f"{r}.json").read_text())["pid"] for r in ("api", "web", "supervisor")]
        proc.send_signal(signal.SIGINT)
        assert proc.wait(timeout=30) == 0
        time.sleep(0.5)
        assert not [p for p in pids if E.pid_alive(p)], "services left running after Ctrl+C"
        assert not list(E.PIDS.glob("*.json")) or all(not (E.PIDS / f"{r}.json").exists() for r in ("api", "web", "supervisor"))
        assert E.port_free(api_port) and E.port_free(web_port)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
