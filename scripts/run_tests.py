"""``./mirage test``: pytest stays authoritative; this groups its results for humans and keeps
SOFTWARE failures distinct from SCIENTIFIC VALIDATION gates. Standard library only.

    ./mirage test --quick        imports, contracts, trust boundary, API, E2E smoke, essential frontend (~1-2 min)
    ./mirage test                every software group, then the validation gates
    ./mirage test --scientific   only the scientific validation gates and benchmark invariants

A gate that does not pass is reported as NOT PASSED and never as PASS. A gate listed in
``KNOWN_GATE_FAILURES`` is additionally labelled KNOWN SCIENTIFIC VALIDATION FAILURE with the
document that records it; an unlisted failing gate is labelled NEW.

Exit codes: 0 all clear; 1 a software failure; 2 software clear but a validation gate is NOT PASSED.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import mirage_env as E

T = "tests"
LOCK_TESTS = (
    f"{T}/campaign/test_campaign_rescue_v2.py::test_committed_lock_matches_the_files_on_disk",
    f"{T}/campaign/test_campaign_rescue_v2.py::test_lock_detects_any_change_to_spec_scoring_or_doc",
)
CONVERGENCE = f"{T}/belief/test_belief_convergence_gate.py"
TRUST_FILES = (f"{T}/test_trust_boundary.py", f"{T}/belief/test_belief_trust_boundary.py", f"{T}/api/test_api_leakage.py")


@dataclass
class Group:
    key: str
    title: str
    paths: list[str]
    deselect: list[str] = field(default_factory=list)
    gate: bool = False  # a scientific validation criterion, not a software contract
    quick: bool = False
    kind: str = "pytest"  # pytest | frontend | e2e
    args: list[str] = field(default_factory=list)  # extra pytest args (e.g. -m "not slow" in quick mode)


# Known, documented gate failures on main. These explain a NOT PASSED; they never turn it into PASS.
KNOWN_GATE_FAILURES = {
    "b4a": "declared posterior-convergence gate is not met at any tested particle count; gate was not relaxed (docs/validation/B4A_CONVERGENCE_RESULTS.md)",
    "prereg": "Binder Rescue V2 hash lock no longer matches evaluation/campaign/truth.py after A5 (docs/evaluation/BINDER_RESCUE_V2_STATUS.md)",
}


def build_groups() -> list[Group]:
    claimed = {CONVERGENCE, *TRUST_FILES}
    groups = [
        Group("core", "CORE CONTRACTS", [f"{T}/core", f"{T}/test_import.py", f"{T}/test_config.py"], quick=True),
        Group("binder", "BINDER ENVIRONMENT", [f"{T}/binder"]),
        Group("belief", "BELIEF SOFTWARE", [f"{T}/belief"], deselect=[CONVERGENCE, f"{T}/belief/test_belief_trust_boundary.py"]),
        Group("b4a", "B4A CONVERGENCE GATE", [CONVERGENCE], gate=True),
        Group("policies", "POLICIES", [f"{T}/policies"]),
        Group("trust", "TRUST BOUNDARY", list(TRUST_FILES), quick=True),
        Group("evaluator", "EVALUATOR", [f"{T}/campaign"], deselect=list(LOCK_TESTS)),
        Group("prereg", "V2 PREREGISTRATION LOCK", list(LOCK_TESTS), gate=True),
        Group("api", "API", [f"{T}/api", f"{T}/integration"], deselect=[f"{T}/api/test_api_leakage.py"], quick=True),
        Group("rl", "RL", [f"{T}/rl"]),
        Group("dx", "LAUNCHER (DX)", [f"{T}/dx"], quick=True),
    ]
    for g in groups:
        claimed.update(g.paths)
    claimed_dirs = {p for p in claimed if not p.endswith(".py") and "::" not in p}
    leftovers = []
    for f in sorted((E.ROOT / T).rglob("test_*.py")):
        rel = f.relative_to(E.ROOT).as_posix()
        if rel in claimed or any(rel.startswith(d + "/") for d in claimed_dirs) or any(rel.startswith(p.split("::")[0]) for p in claimed if "::" in p):
            continue
        leftovers.append(rel)
    groups.append(Group("legacy", "PROVENANCE + LEGACY BIO", leftovers))
    groups.append(Group("frontend", "FRONTEND", [], quick=True, kind="frontend"))
    groups.append(Group("e2e", "END-TO-END SMOKE", [], quick=True, kind="e2e"))
    return groups


def scientific_groups() -> list[Group]:
    return [
        Group("b4a", "B4A CONVERGENCE VALIDATION", [CONVERGENCE], gate=True),
        Group("semantics", "SCENARIO SEMANTICS V2", [f"{T}/binder/test_scenario_semantics_v2.py"], gate=True),
        Group("model", "MODEL CONSISTENCY", [f"{T}/binder/test_predictive.py", f"{T}/belief/test_belief_directional.py"], gate=True),
        Group("invariants", "BENCHMARK INVARIANTS", [f"{T}/campaign/test_campaign_baseline_export.py", f"{T}/campaign/test_campaign_aggregate.py", f"{T}/campaign/test_campaign_harness.py"], gate=True),
        Group("prereg", "V2 PREREGISTRATION LOCK", list(LOCK_TESTS), gate=True),
    ]


@dataclass
class Result:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    seconds: float = 0.0
    failures: list[str] = field(default_factory=list)
    detail: str = ""
    ran: bool = True

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def ok(self) -> bool:
        return self.ran and self.failed == 0 and self.errors == 0


_COUNT = re.compile(r"(\d+) (failed|passed|skipped|xfailed|xpassed|errors?|warnings?|deselected)")


def run_pytest(paths: list[str], deselect: list[str], extra: list[str] | None = None) -> Result:
    argv = [str(E.venv_python()), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE", "--no-header", "-W", "ignore::DeprecationWarning", *(extra or []), *paths]
    for d in deselect:
        argv += ["--deselect", d]
    started = time.time()
    proc = E.run(argv, cwd=E.ROOT, env=E.project_env())
    out = proc.stdout or ""
    res = Result(seconds=time.time() - started)
    last = next((ln for ln in reversed(out.splitlines()) if re.search(r"\b(passed|failed|error|errors|skipped|no tests ran)\b.* in [\d.]+s", ln)), "")
    counts = {k.rstrip("s") if k.startswith("error") else k: int(n) for n, k in _COUNT.findall(last)}
    res.passed, res.failed, res.errors, res.skipped = counts.get("passed", 0), counts.get("failed", 0), counts.get("error", 0), counts.get("skipped", 0)
    res.failures = [ln.split(" ", 1)[1].split(" - ")[0] for ln in out.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
    if not last or (proc.returncode not in (0, 1) and not res.failures):
        res.errors = max(res.errors, 1)
        res.detail = "\n".join(out.splitlines()[-15:])
    return res


def _npm(script: str) -> subprocess.CompletedProcess:
    return E.run(["npm", "run", "--silent", script], cwd=E.FRONTEND, env=E.project_env(), timeout=900)


def run_frontend(quick: bool) -> Result:
    started = time.time()
    res = Result()
    steps = ["typecheck", "test"] if quick else ["typecheck", "lint", "test", "build"]
    if not E.frontend_deps_ready():
        return Result(ran=False, detail="frontend dependencies not installed (run ./mirage setup)")
    marks = []
    for step in steps:
        proc = _npm(step)
        out = proc.stdout or ""
        if step == "test":
            m = re.search(r"Tests\s+(?:(\d+) failed\s*\|\s*)?(\d+) passed(?:\s*\|\s*(\d+) skipped)?", out)
            if m:
                res.failed, res.passed, res.skipped = int(m.group(1) or 0), int(m.group(2)), int(m.group(3) or 0)
        if proc.returncode != 0:
            res.failures.append(f"npm run {step}")
            res.detail += f"\n── npm run {step} ──\n" + "\n".join(out.splitlines()[-25:])
            marks.append(f"{step} ✗")
        else:
            marks.append(f"{step} ✓")
    res.seconds = time.time() - started
    res.detail = (" · ".join(marks)) + res.detail
    if res.failures and res.failed == 0:
        res.errors = len(res.failures)
    return res


def run_e2e() -> Result:
    """Real server process, real sockets: reset -> recommend -> act -> replay -> verdict."""
    started = time.time()
    port = E.find_free_port(18000)
    token = secrets.token_urlsafe(12)
    log = E.LOGS / "e2e-api.log"
    E.LOGS.mkdir(parents=True, exist_ok=True)
    records = E.LOCAL / "e2e-records"
    base = f"http://127.0.0.1:{port}"
    steps: list[str] = []

    def call(method: str, path: str, body=None, headers=None):
        req = urllib.request.Request(base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - loopback
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, None

    with open(log, "w") as fh:
        proc = subprocess.Popen([str(E.venv_python()), "scripts/serve_api.py", "--port", str(port), "--records", str(records), "--log-level", "warning"],
                                cwd=E.ROOT, env=E.project_env({"MIRAGE_EVAL_TOKEN": token}), stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if not _wait_health(base, proc):
            return Result(errors=1, seconds=time.time() - started, detail=f"API did not start:\n{E.tail(log)}")
        checks = []

        def expect(name: str, cond: bool) -> None:
            checks.append(name)
            if not cond:
                raise AssertionError(name)

        expect("health", call("GET", "/health")[0] == 200)
        _, version = call("GET", "/version")
        expect("version/semantics", bool(version) and version["scenario_semantics_default"] == "SEMANTICS_V2")
        _, policies = call("GET", "/policies")
        expect("policy catalogue", {p["name"] for p in policies if p["available"]} >= {"rescue_planner", "greedy_eig", "fixed_pipeline", "random"})
        status, state = call("POST", "/episodes", {"seed": 9, "policy_name": "rescue_planner", "scenario": "aggregation_kinetic_defect", "scenario_version": "SEMANTICS_V2"})
        expect("reset episode", status == 201)
        eid = state["episode_id"]
        terminal, actions = False, []
        for _ in range(12):
            _, rec = call("GET", f"/episodes/{eid}/recommendation")
            _, step = call("POST", f"/episodes/{eid}/actions", rec["action"])
            actions.append(rec["action"]["action_type"])
            if step["state"]["terminal"]:
                terminal = True
                break
        expect("campaign reaches a decision", terminal)
        status, replay = call("GET", f"/episodes/{eid}/replay")
        expect("replay complete + version recorded", status == 200 and replay["complete"] and replay["environment_id"].endswith("/SEMANTICS_V2") and replay["seed"] == 9)
        expect("verdict refused without token", call("GET", f"/benchmarks/episodes/{eid}")[0] == 403)
        status, verdict = call("GET", f"/benchmarks/episodes/{eid}", headers={"X-Mirage-Eval-Token": token})
        expect("verdict with token", status == 200 and "justified" in verdict)
        status, diag = call("GET", "/diagnostics")
        expect("diagnostics", status == 200 and diag["status"] == "ok")
        steps = checks
        return Result(passed=len(steps), seconds=time.time() - started, detail=" → ".join(a.removeprefix("MEASURE_").lower() for a in actions))
    except AssertionError as exc:
        return Result(passed=len(steps), failed=1, failures=[f"e2e: {exc}"], seconds=time.time() - started, detail=E.tail(log, 10))
    except Exception as exc:  # noqa: BLE001
        return Result(errors=1, seconds=time.time() - started, detail=f"{type(exc).__name__}: {exc}\n{E.tail(log, 10)}")
    finally:
        E.terminate_group(proc.pid, grace=4)
        proc.wait(timeout=5)


def _wait_health(base: str, proc: subprocess.Popen, timeout: float = 60) -> bool:
    end = time.time() + timeout
    while time.time() < end and proc.poll() is None:
        if (E.http_json(base + "/health") or {}).get("status") == "ok":
            return True
        time.sleep(0.4)
    return False


# ------------------------------------------------------------------ reporting
def classify(group: Group, res: Result) -> tuple[str, str]:
    """(label, note). Gates never read FAIL; software never reads NOT PASSED."""
    if not res.ran:
        return "SKIP", res.detail
    if res.ok:
        return "PASS", ""
    if group.gate:
        known = KNOWN_GATE_FAILURES.get(group.key)
        return "NOT PASSED", ("KNOWN SCIENTIFIC VALIDATION FAILURE: " + known) if known else "NEW: not in the known-failure registry; investigate before trusting results"
    return "FAIL", ""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mirage test")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--scientific", action="store_true")
    ap.add_argument("--list", action="store_true", help="show groups and exit")
    ap.add_argument("--only", help="comma-separated group keys")
    ns = ap.parse_args(argv)
    groups = scientific_groups() if ns.scientific else build_groups()
    if ns.quick:
        groups = [g for g in groups if g.quick]
    if ns.only:
        wanted = set(ns.only.split(","))
        groups = [g for g in groups if g.key in wanted]
    if ns.list:
        for g in groups:
            print(f"{g.key:<11}{g.title:<30}{'gate' if g.gate else 'software':<9}{' '.join(g.paths) or g.kind}")
        return 0
    if not E.venv_python().exists():
        E.fail("no .venv yet. Run: ./mirage setup")
        return 1

    mode = "scientific validation" if ns.scientific else "quick" if ns.quick else "full"
    E.banner(f"Tests · {mode}")
    print(E.paint("pytest is authoritative; software failures and scientific validation gates are reported separately.", "dim"))
    print()
    started = time.time()
    rows: list[tuple[Group, str, str, Result]] = []
    for g in groups:
        if sys.stdout.isatty():
            sys.stdout.write(E.paint(f"  running {g.title.lower()}...", "dim") + "\r")
            sys.stdout.flush()
        extra = g.args + (["-m", "not slow"] if ns.quick and g.kind == "pytest" else [])
        res = run_pytest(g.paths, g.deselect, extra) if g.kind == "pytest" else run_frontend(ns.quick) if g.kind == "frontend" else run_e2e()
        label, note = classify(g, res)
        rows.append((g, label, note, res))
        counts = f"{res.passed}/{res.total}" if res.ran and res.total else ""
        extra = f"  ({res.skipped} skipped)" if res.skipped else ""
        colour = {"PASS": "green", "FAIL": "red", "NOT PASSED": "yellow", "SKIP": "dim"}[label]
        print(f"{g.title.ljust(28)}{E.paint(label.ljust(11), colour, 'bold')}{counts.ljust(10)}{E.paint(f'{res.seconds:5.1f}s', 'dim')}{extra}" + " " * 12)

    print()
    problems = [(g, r, res) for g, r, _, res in rows if r == "FAIL"]
    gates = [(g, n, res) for g, r, n, res in rows if r == "NOT PASSED"]
    for g, _, res in problems:
        print(E.paint(f"software failure in {g.title}:", "red", "bold"))
        for f in res.failures[:12]:
            print(f"    {f}")
        if res.detail:
            print("    " + res.detail.replace("\n", "\n    "))
    for g, note, res in gates:
        print(E.paint(f"{g.title}: NOT PASSED", "yellow", "bold"))
        print(f"    {note}")
        for f in res.failures[:6]:
            print(f"    failing: {f}")
    for g, r, note, res in rows:
        if r == "SKIP":
            print(E.paint(f"skipped {g.title}: {note}", "dim"))
    elapsed = time.time() - started
    print()
    if problems:
        print(E.paint(f"SOFTWARE FAILURES: {len(problems)} group(s) failed ({elapsed:.0f}s)", "red", "bold"))
        return 1
    if gates:
        print(E.paint(f"Software is clear. {len(gates)} scientific validation gate(s) NOT PASSED; they are science, not bugs, and are not hidden ({elapsed:.0f}s).", "yellow", "bold"))
        return 2
    print(E.paint(f"ALL CLEAR ({elapsed:.0f}s)", "green", "bold"))
    return 0
