"""Driver for the measurement-price experiment (exploratory; see REGISTRATION.md).

Usage (from the repository root):

  PYTHONPATH=src .venv/bin/python experiments/exploratory/cost-sensitivity/driver.py dryrun
  PYTHONPATH=src .venv/bin/python experiments/exploratory/cost-sensitivity/driver.py run
  PYTHONPATH=src .venv/bin/python experiments/exploratory/cost-sensitivity/driver.py spend

``run`` executes the strong matrix interleaved (for each seed: P1, P3, P6) into
``runs/<run_id>`` and is resumable: finished episode files are never rewritten. It mirrors
``mirage.evaluation.runner.run`` (manifest, API_FAILURE re-run once, summarize) but builds a
``PricedLabEnvironment`` / ``PricedClaudeAgent``. Every API call's token usage is written to
``runs/<run_id>/usage.jsonl`` and to the session ledger ``ledger.jsonl``; the driver stops
before an episode that could take the session past the registered spend cap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mirage.biology.conditions import Condition  # noqa: E402
from mirage.config import EpisodeConfig, canonical_sha256, load_prior, sample_episode  # noqa: E402
from mirage.evaluation import report, runner  # noqa: E402
from mirage.evaluation.metrics import (  # noqa: E402
    SCHEMA_VERSION,
    DiagnosticActionSet,
    EpisodeResult,
    audit_measurements,
    score_episode,
)
from mirage.lab.tools import BUDGET_UNITS  # noqa: E402
from priced import PRICES, PricedClaudeAgent, PricedLabEnvironment  # noqa: E402

MODEL = "claude-sonnet-5-5"
# USD per million tokens, public Anthropic pricing page (Claude Sonnet 5.5), fetched at
# registration: base input, output, 5-minute cache write, cache read.
PRICING_USD_PER_MTOK = {
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_write": 2.5, "cache_read": 0.2},
}
CAP_USD = 5.00
STOP_USD = 4.75
MIN_EPISODE_RESERVE_USD = 0.10

RUNS = HERE / "runs"
DRYRUN = HERE / "dryrun"
LEDGER = HERE / "ledger.jsonl"
MATRIX_NAME = "strong"
DRY_EPISODES = (  # dev block 0-9999: pipeline check only, never reported
    (0, Condition.BIOLOGICAL_PLATEAU, 1),
    (1, Condition.MEASUREMENT_ARTIFACT, 3),
    (2, Condition.BIOLOGICAL_PLATEAU, 6),
)


def run_id_for(price: int, prefix: str = "") -> str:
    return f"{prefix}sonnet55_price{price}_{MATRIX_NAME if not prefix else 'dev'}"


# ---- spend accounting -------------------------------------------------------------------


def call_cost_usd(model: str, usage: dict[str, int]) -> float:
    p = PRICING_USD_PER_MTOK[model]
    return (
        usage.get("input_tokens", 0) * p["input"]
        + usage.get("output_tokens", 0) * p["output"]
        + usage.get("cache_write", 0) * p["cache_write"]
        + usage.get("cache_read", 0) * p["cache_read"]
    ) / 1e6


def ledger_spent(path: Path = LEDGER) -> float:
    if not path.exists():
        return 0.0
    return sum(json.loads(line)["usd"] for line in path.read_text().splitlines() if line.strip())


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


class SpendGuard:
    """Stops before an episode that could push the session past ``stop_usd``."""

    def __init__(self, spent: float, stop_usd: float = STOP_USD,
                 min_reserve: float = MIN_EPISODE_RESERVE_USD) -> None:
        self.spent = spent
        self.stop_usd = stop_usd
        self.max_episode = min_reserve

    def may_start(self) -> bool:
        # Reserve two episodes: an API_FAILURE triggers one re-run.
        return self.spent + 2 * self.max_episode <= self.stop_usd

    def record_episode(self, usd: float) -> None:
        self.max_episode = max(self.max_episode, usd)


class MeteredClient:
    """Wraps an Anthropic client; logs token usage per call (no headers, no credentials)."""

    def __init__(self, inner: Any, on_usage: Callable[[dict[str, Any]], None]) -> None:
        self._inner = inner
        self._on_usage = on_usage
        self.messages = self

    def create(self, **params: Any) -> Any:
        t0 = time.monotonic()
        response = self._inner.messages.create(**params)
        u = response.usage
        self._on_usage({
            "model": response.model,
            "stop_reason": response.stop_reason,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cache_read": getattr(u, "cache_read_input_tokens", None) or 0,
            "cache_write": getattr(u, "cache_creation_input_tokens", None) or 0,
            "s": round(time.monotonic() - t0, 1),
        })
        return response


# ---- episodes ---------------------------------------------------------------------------


def run_priced_episode(cfg: EpisodeConfig, agent: PricedClaudeAgent, dset: DiagnosticActionSet,
                       run_meta: dict[str, Any]) -> EpisodeResult:
    """``runner.run_episode`` with a ``PricedLabEnvironment``; scoring is the frozen one."""
    env = PricedLabEnvironment(cfg, price=agent.price)
    started = runner._now()
    agent.run(env.session())
    if not env.finished:
        env.finish(agent.outcome or "NO_DIAGNOSIS")
    audit = audit_measurements(cfg, env.events, dset)
    return EpisodeResult(
        schema_version=SCHEMA_VERSION,
        episode=cfg,
        agent=runner.agent_info(agent),
        passive=env.passive,
        events=env.events,
        diagnosis=env.diagnosis,
        status=env.status,
        audit=audit,
        scores=score_episode(cfg, env.events, env.diagnosis, audit),
        llm_transcript=list(agent.transcript),
        versions=runner.versions(),
        run_meta={**run_meta, "started_at": started, "finished_at": runner._now()},
    )


def _manifest(run_id: str, matrix_name: str, matrix_sha: str, prior, dset, agent,
              n: int) -> dict[str, Any]:
    return {
        "run_id": run_id, "agent": "claude", "matrix": matrix_name,
        "matrix_sha256": matrix_sha, "scenario_sha256": canonical_sha256(prior),
        "gate0_summary_sha256": runner.file_sha256(runner.GATE0_SUMMARY),
        "diagnostic_action_set": dset.model_dump(mode="json"),
        "prompt_version": agent.prompt_version, "n_episodes": n,
        "versions": runner.versions(), "created_at": runner._now(),
        "model": agent.model, "effort": agent.effort, "prompt_sha256": agent.prompt_sha256,
        "exploratory": "experiments/exploratory/cost-sensitivity (not a frozen result)",
        "driver": "experiments/exploratory/cost-sensitivity/driver.py",
        "price_units_per_replicate": agent.price, "budget_units": BUDGET_UNITS,
    }


def run_interleaved(
    episodes: list[tuple[int, Condition, tuple[int, ...]]],
    out_root: Path,
    matrix_name: str,
    matrix_sha: str,
    *,
    run_ids: dict[int, str],
    client: Any | None = None,
    model: str = MODEL,
    ledger: Path = LEDGER,
    guard: SpendGuard | None = None,
) -> dict[str, Any]:
    """Run each ``(seed, condition, prices)`` entry at each listed price, in order.

    Resumable: existing episode files are skipped. Returns a small status dict.
    """
    if client is None:
        if not os.environ.get(runner.API_KEY_ENV):
            raise ValueError(f"{runner.API_KEY_ENV} is not set; refusing to start a paid run")
        from mirage.agents.claude import make_client

        client = make_client()
    guard = guard or SpendGuard(ledger_spent(ledger))
    prior = load_prior(runner.SCENARIO)
    dset = runner.frozen_dset(prior, runner.GATE0_SUMMARY)
    prices = sorted({p for _, _, ps in episodes for p in ps})
    counts = {p: sum(p in ps for _, _, ps in episodes) for p in prices}
    current: dict[str, Any] = {}

    def on_usage(row: dict[str, Any]) -> None:
        usd = call_cost_usd(row["model"], row)
        full = {**row, "episode_id": current["episode_id"], "attempt": current["attempt"]}
        _append(current["run_dir"] / "usage.jsonl", full)
        _append(ledger, {**full, "run_id": current["run_id"], "usd": usd})
        guard.spent += usd
        current["usd"] += usd

    metered = MeteredClient(client, on_usage)
    agents = {p: PricedClaudeAgent(metered, price=p, model=model) for p in prices}
    for p in prices:
        run_dir = out_root / run_ids[p]
        manifest = _manifest(run_ids[p], matrix_name, matrix_sha, prior, dset, agents[p],
                             counts[p])
        path = run_dir / "manifest.json"
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            changed = sorted(k for k in manifest if k not in ("created_at", "versions")
                             and manifest[k] != old.get(k))
            if changed:
                raise ValueError(f"cannot resume {run_ids[p]}: manifest differs in {changed}")
        else:
            runner.write_atomic(path, runner.dumps(manifest))

    stopped = None
    for seed, condition, ps in episodes:
        cfg = sample_episode(prior, seed, condition)
        for p in ps:
            run_dir = out_root / run_ids[p]
            episode_path = run_dir / "episodes" / f"{cfg.episode_id}.json"
            attempt1 = run_dir / "reruns" / f"{cfg.episode_id}.attempt1.json"
            if episode_path.exists():
                continue
            if not guard.may_start():
                stopped = f"spend guard before {cfg.episode_id} at P{p} (spent {guard.spent:.4f})"
                break
            meta = {"run_id": run_ids[p], "price_units_per_replicate": p}
            current.update(run_dir=run_dir, run_id=run_ids[p], episode_id=cfg.episode_id,
                           attempt=2 if attempt1.exists() else 1, usd=0.0)
            res = run_priced_episode(cfg, agents[p], dset, meta)
            if res.status == "API_FAILURE" and not attempt1.exists():
                runner.write_atomic(attempt1, runner.dumps(res.model_dump(mode="json")))
                current["attempt"] = 2
                res = run_priced_episode(cfg, agents[p], dset, meta)
            guard.record_episode(current["usd"])
            runner.write_atomic(episode_path, runner.dumps(res.model_dump(mode="json")))
            print(f"{run_ids[p]} {cfg.episode_id} {res.status} correct={res.scores.correct} "
                  f"control={res.scores.diagnostic_control} usd={current['usd']:.4f} "
                  f"session={guard.spent:.4f}", flush=True)
        if stopped:
            break
    for p in prices:
        finalize(out_root / run_ids[p])
    return {"stopped": stopped, "spent_usd": guard.spent}


def finalize(run_dir: Path) -> None:
    """Record re-runs in the manifest, then the frozen summarize and report."""
    if not any((run_dir / "episodes").glob("*.json")):
        return
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["reruns"] = {
        p.name.removesuffix(".attempt1.json"): f"reruns/{p.name}"
        for p in sorted((run_dir / "reruns").glob("*.attempt1.json"))
    }
    runner.write_atomic(manifest_path, runner.dumps(manifest))
    runner.summarize(run_dir)
    # Existing report generator; the run occupies its fixed "C2 Claude Sonnet 5.5" slot.
    report.build_report({"claude_c2": run_dir}, run_dir)


def strong_episodes() -> list[tuple[int, Condition, tuple[int, ...]]]:
    return [(s, c, PRICES) for s, c in runner.load_matrix(runner.MATRIX, MATRIX_NAME)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cost-sensitivity-driver")
    ap.add_argument("cmd", choices=("dryrun", "run", "spend", "finalize"))
    args = ap.parse_args(argv)
    if args.cmd == "spend":
        print(f"session spend USD {ledger_spent():.4f} (cap {CAP_USD:.2f}, stop {STOP_USD:.2f})")
        return 0
    if args.cmd == "finalize":
        for p in PRICES:
            finalize(RUNS / run_id_for(p))
        return 0
    if args.cmd == "dryrun":
        eps = [(s, c, (p,)) for s, c, p in DRY_EPISODES]
        sha = hashlib.sha256(json.dumps([[s, c.value, p] for s, c, p in DRY_EPISODES])
                             .encode()).hexdigest()
        out = run_interleaved(eps, DRYRUN, "dev-dryrun", sha,
                              run_ids={p: run_id_for(p, "dryrun_") for _, _, p in DRY_EPISODES})
    else:
        out = run_interleaved(strong_episodes(), RUNS, MATRIX_NAME,
                              runner.file_sha256(runner.MATRIX),
                              run_ids={p: run_id_for(p) for p in PRICES})
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
