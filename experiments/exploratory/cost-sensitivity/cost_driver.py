"""Exploratory MIRAGE-Bio driver for higher per-replicate measurement prices."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
from pydantic import ValidationError

from mirage.agents import claude as claude_module
from mirage.agents.claude import ClaudeAgent
from mirage.agents.scripted import (
    GOOD_SCIENTIST_NOTES,
    PLATEAU_TIMES_H,
    TAU,
    _call,
    _passive_by_time,
)
from mirage.assay.od_reader import read, response
from mirage.config import EpisodeConfig, sample_episode
from mirage.evaluation import report, runner
from mirage.evaluation.metrics import EpisodeResult, audit_measurements, score_episode
from mirage.lab.environment import (
    MEASUREMENT_STREAM,
    AcceptedMeasurement,
    LabEnvironment,
    _one_line,
)
from mirage.lab.tools import (
    BUDGET_UNITS,
    MAX_TURNS,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
    MeasurementRequest,
    MeasurementResult,
    Observation,
    render_measurement,
    render_observation,
)

PRICES = (1, 3, 6)
MODEL = "claude-sonnet-5-5"
PRICING_USD_PER_MTOK = {
    "input": 2.0,
    "output": 10.0,
    "cache_write": 2.5,
    "cache_read": 0.20,
}
SPEND_CAP_USD = 5.0
RESERVE_USD = 0.15
HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"


def _validate_price(c: int) -> int:
    if type(c) is not int or c < 1:
        raise ValueError(f"unit price must be an integer >= 1, got {c!r}")
    return c


def priced_system_prompt(c: int) -> str:
    c = _validate_price(c)
    if c == 1:
        return SYSTEM_PROMPT
    old = "each replicate reading\ncosts 1 unit from a budget of 6 units"
    assert SYSTEM_PROMPT.count(old) == 1
    return SYSTEM_PROMPT.replace(
        old, f"each replicate reading\ncosts {c} units from a budget of 6 units"
    )


def priced_tools(c: int) -> list[dict[str, Any]]:
    c = _validate_price(c)
    tools = copy.deepcopy(TOOL_DEFINITIONS)
    if c > 1:
        tool = next(t for t in tools if t["name"] == "measure_od")
        old = "and costs 1 budget unit."
        assert tool["description"].count(old) == 1
        tool["description"] = tool["description"].replace(
            old, f"and costs {c} budget units."
        )
    return tools


def priced_prompt_sha256(c: int) -> str:
    payload = json.dumps(
        {"system": priced_system_prompt(c), "tools": priced_tools(c)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prompt_version(c: int) -> str:
    c = _validate_price(c)
    return PROMPT_VERSION if c == 1 else f"{PROMPT_VERSION}-price{c}x"


def render_priced_observation(obs: Observation, c: int) -> str:
    c = _validate_price(c)
    if c == 1:
        return render_observation(obs)
    payload = json.loads(render_observation(obs))
    assert payload["budget"]["cost"] == "1 unit per replicate reading"
    payload["budget"]["cost"] = f"{c} units per replicate reading"
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)


class PricedLabEnvironment(LabEnvironment):
    def __init__(
        self,
        config: EpisodeConfig,
        *,
        unit_price: int,
        max_turns: int = MAX_TURNS,
    ) -> None:
        self.unit_price = _validate_price(unit_price)
        super().__init__(config, max_turns=max_turns)

    def _measure(self, index: int, args: dict[str, Any]) -> tuple[dict | None, str | None]:
        try:
            req = MeasurementRequest(**args)
        except ValidationError as err:
            return None, _one_line(err)
        cost = req.replicates * self.unit_price
        if cost > self.budget_remaining:
            if self.unit_price == 1:
                return None, (
                    f"replicates ({req.replicates}) exceeds remaining budget "
                    f"({self.budget_remaining})"
                )
            return None, (
                f"replicates ({req.replicates}) cost {cost} units, which exceeds "
                f"remaining budget ({self.budget_remaining} units)"
            )
        request_index = len(self.accepted)
        x = self.latent(req.time_h)
        presented = x / req.dilution_factor
        rng = self._stream(MEASUREMENT_STREAM, request_index)
        readings = read(
            np.full(req.replicates, presented), rng, **self._assay_kwargs()
        )
        a = self.config.assay
        noise_free = float(response(presented, s_odeq=a.s_odeq, n=a.n))
        self.budget_remaining -= cost
        self.accepted.append(
            AcceptedMeasurement(
                event_index=index,
                request_index=request_index,
                time_h=req.time_h,
                dilution_factor=req.dilution_factor,
                replicates=req.replicates,
                latent_biomass_odeq=x,
                presented_biomass_odeq=presented,
                noise_free_reading=noise_free,
            )
        )
        res = MeasurementResult(
            source="agent",
            request_index=request_index,
            time_h=req.time_h,
            dilution_factor=req.dilution_factor,
            readings=[float(y) for y in readings],
            mean_reading=round(float(np.mean(readings)), 4),
            cost_units=cost,
            budget_remaining=self.budget_remaining,
        )
        self.measurements.append(res)
        return render_measurement(res), None


class PricedClaudeAgent(ClaudeAgent):
    def __init__(
        self,
        client: Any | None = None,
        *,
        unit_price: int,
        model: str = MODEL,
        max_turns: int = MAX_TURNS,
    ) -> None:
        self.unit_price = _validate_price(unit_price)
        super().__init__(client, model=model, max_turns=max_turns)
        self.prompt_version = prompt_version(self.unit_price)
        self.prompt_sha256 = priced_prompt_sha256(self.unit_price)

    def request_params(self, messages: list[Any]) -> dict[str, Any]:
        params = super().request_params(messages)
        params["system"] = priced_system_prompt(self.unit_price)
        params["tools"] = priced_tools(self.unit_price)
        return params

    def run(self, session: Any) -> None:
        with patch.object(
            claude_module,
            "render_observation",
            lambda obs: render_priced_observation(obs, self.unit_price),
        ):
            super().run(session)


class PricedGoodScientist:
    name = "PricedGoodScientist"

    def __init__(self, unit_price: int) -> None:
        self.unit_price = _validate_price(unit_price)

    def run(self, session: Any) -> None:
        _call(
            session,
            self.name,
            "declare_state",
            {"notes": GOOD_SCIENTIST_NOTES, "p_biomass_above_reading": 0.5},
        )
        passive = _passive_by_time(session)
        p_hat = float(np.mean([passive[t] for t in PLATEAU_TIMES_H]))
        replicates = min(3, BUDGET_UNITS // self.unit_price)
        res = _call(
            session,
            self.name,
            "measure_od",
            {
                "time_h": 18,
                "dilution_factor": 10.0,
                "replicates": replicates,
            },
        )
        c_hat = 10.0 * float(np.mean(res["readings"]))
        ratio = c_hat / p_hat
        continued = ratio >= TAU
        _call(
            session,
            self.name,
            "submit_diagnosis",
            {
                "diagnosis": (
                    "BIOMASS_ABOVE_READING" if continued else "BIOMASS_AS_READ"
                ),
                "p_biomass_above_reading": 0.99 if continued else 0.01,
                "late_biomass_estimate_od": c_hat,
                "rationale": (
                    f"1:10 corrected late OD {c_hat:.4f} / passive plateau "
                    f"{p_hat:.4f} = {ratio:.3f} {'>=' if continued else '<'} {TAU}."
                ),
            },
        )


class UsageLoggingClient:
    def __init__(self, client: Any | None = None, *, path: Path) -> None:
        self._client = client
        self.path = path
        self.messages = self

    def create(self, **params: Any) -> Any:
        client = self._client
        if client is None:
            client = claude_module.make_client()
            self._client = client
        started = time.perf_counter()
        response = client.messages.create(**params)
        seconds = round(time.perf_counter() - started, 1)
        usage = response.usage

        def value(name: str) -> int:
            return int(getattr(usage, name, None) or 0)

        record = {
            "model": response.model,
            "stop_reason": response.stop_reason,
            "input_tokens": value("input_tokens"),
            "output_tokens": value("output_tokens"),
            "cache_read": value("cache_read_input_tokens"),
            "cache_write": value("cache_creation_input_tokens"),
            "s": seconds,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        return response


def spend_usd(root: Path = RUNS) -> float:
    total = 0.0
    for path in root.rglob("usage.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            total += sum(
                row.get(key, 0) * rate
                for key, rate in (
                    ("input_tokens", PRICING_USD_PER_MTOK["input"]),
                    ("output_tokens", PRICING_USD_PER_MTOK["output"]),
                    ("cache_write", PRICING_USD_PER_MTOK["cache_write"]),
                    ("cache_read", PRICING_USD_PER_MTOK["cache_read"]),
                )
            ) / 1_000_000
    return total


def run_priced_episode(
    cfg: EpisodeConfig,
    agent: Any,
    dset: Any,
    meta: dict[str, Any],
    unit_price: int,
) -> EpisodeResult:
    env = PricedLabEnvironment(cfg, unit_price=unit_price)
    started = runner._now()
    agent.run(env.session())
    llm = runner.is_llm(agent)
    if not env.finished:
        env.finish((agent.outcome if llm else None) or "NO_DIAGNOSIS")
    audit = audit_measurements(cfg, env.events, dset)
    return EpisodeResult(
        schema_version="episode-result-v2",
        episode=cfg,
        agent=runner.agent_info(agent),
        passive=env.passive,
        events=env.events,
        diagnosis=env.diagnosis,
        status=env.status,
        audit=audit,
        scores=score_episode(cfg, env.events, env.diagnosis, audit),
        llm_transcript=list(agent.transcript) if llm else None,
        versions=runner.versions(),
        run_meta={**meta, "started_at": started, "finished_at": runner._now()},
    )


def run_arm(
    agent_kind: str,
    unit_price: int,
    matrix_name: str,
    out_root: Path = RUNS,
    *,
    matrix_file: Path = runner.MATRIX,
    run_id: str | None = None,
    client: Any | None = None,
    model: str = MODEL,
    resume: bool = False,
    spend_root: Path = RUNS,
    cap: float = SPEND_CAP_USD,
    reserve: float = RESERVE_USD,
) -> Path:
    unit_price = _validate_price(unit_price)
    if agent_kind not in {"claude", "good_scientist"}:
        raise ValueError("agent_kind must be 'claude' or 'good_scientist'")
    if agent_kind != "claude" and model != MODEL:
        raise ValueError("--model is only supported with --agent claude")
    if resume and not run_id:
        raise ValueError("--resume needs the RUN_ID of the run to continue")
    prior = runner.load_prior(runner.SCENARIO)
    dset = runner.frozen_dset(prior, runner.GATE0_SUMMARY)
    cfgs = [
        sample_episode(prior, seed, condition)
        for seed, condition in runner.load_matrix(matrix_file, matrix_name)
    ]
    if agent_kind == "claude" and client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError(
            f"{runner.API_KEY_ENV} is not set; refusing to start a paid run without it"
        )
    run_id = run_id or (
        f"{datetime.now(UTC):%Y%m%d-%H%M}_{agent_kind}_{matrix_name}"
        f"_price{unit_price}x"
    )
    run_dir = out_root / run_id
    if run_dir.exists() and not resume:
        raise FileExistsError(f"{run_dir} already exists; runs are never overwritten")
    if resume and not (run_dir / "manifest.json").exists():
        raise FileNotFoundError(f"{run_dir} has no manifest.json to resume")

    if agent_kind == "claude":
        agent = PricedClaudeAgent(
            UsageLoggingClient(client, path=run_dir / "usage.jsonl"),
            unit_price=unit_price,
            model=model,
        )
        manifest_agent = "claude"
    else:
        agent = PricedGoodScientist(unit_price)
        manifest_agent = "good_scientist_priced"

    manifest = {
        "run_id": run_id,
        "agent": manifest_agent,
        "matrix": matrix_name,
        "matrix_sha256": runner.file_sha256(matrix_file),
        "scenario_sha256": runner.canonical_sha256(prior),
        "gate0_summary_sha256": runner.file_sha256(runner.GATE0_SUMMARY),
        "diagnostic_action_set": dset.model_dump(mode="json"),
        "prompt_version": PROMPT_VERSION,
        "n_episodes": len(cfgs),
        "versions": runner.versions(),
        "created_at": runner._now(),
        "unit_price": unit_price,
        "budget_units": BUDGET_UNITS,
        "driver": "experiments/exploratory/cost-sensitivity/cost_driver.py",
    }
    if runner.is_llm(agent):
        manifest |= {
            "model": agent.model,
            "effort": agent.effort,
            "prompt_version": agent.prompt_version,
            "prompt_sha256": agent.prompt_sha256,
            "pricing_usd_per_mtok": PRICING_USD_PER_MTOK,
        }
    manifest_path = run_dir / "manifest.json"
    if resume:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        changed = sorted(
            key
            for key in manifest
            if key not in {"created_at", "versions", "reruns", "stopped_early"}
            and manifest[key] != old.get(key)
        )
        if changed:
            raise ValueError(f"cannot resume {run_id}: manifest differs in {', '.join(changed)}")
        base_manifest = old
    else:
        runner.write_atomic(manifest_path, runner.dumps(manifest))
        base_manifest = manifest

    meta = {"run_id": run_id}
    completed = 0
    stopped_early = False
    for cfg in cfgs:
        episode_id = cfg.episode_id
        episode_path = run_dir / "episodes" / f"{episode_id}.json"
        attempt1_path = run_dir / "reruns" / f"{episode_id}.attempt1.json"
        if resume and episode_path.exists():
            completed += 1
            continue
        if agent_kind == "claude":
            spent = spend_usd(spend_root)
            if spent + reserve > cap:
                base_manifest = {
                    **base_manifest,
                    "stopped_early": {
                        "reason": "spend cap",
                        "spent_usd": round(spent, 4),
                        "cap_usd": cap,
                        "completed_episodes": completed,
                    },
                }
                runner.write_atomic(manifest_path, runner.dumps(base_manifest))
                print(
                    f"cost_driver: spend cap reached before {episode_id}; "
                    f"spent ${spent:.4f} of ${cap:.2f}"
                )
                stopped_early = True
                break
        rerun_in_progress = resume and agent_kind == "claude" and attempt1_path.exists()
        result = run_priced_episode(cfg, agent, dset, meta, unit_price)
        if agent_kind == "claude" and result.status == "API_FAILURE" and not rerun_in_progress:
            runner.write_atomic(
                attempt1_path, runner.dumps(result.model_dump(mode="json"))
            )
            result = run_priced_episode(cfg, agent, dset, meta, unit_price)
        runner.write_atomic(
            run_dir / "episodes" / f"{result.episode.episode_id}.json",
            runner.dumps(result.model_dump(mode="json")),
        )
        completed += 1

    if agent_kind == "claude":
        reruns = {
            path.name.removesuffix(".attempt1.json"): f"reruns/{path.name}"
            for path in sorted((run_dir / "reruns").glob("*.attempt1.json"))
        }
        updated = {**base_manifest, "reruns": reruns}
        if stopped_early:
            updated["stopped_early"] = base_manifest["stopped_early"]
        runner.write_atomic(manifest_path, runner.dumps(updated))
    runner.summarize(run_dir)
    if agent_kind == "claude":
        report.build_report({"claude_c2": run_dir}, run_dir)
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cost_driver")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--agent", choices=("claude", "good_scientist"), required=True)
    run_parser.add_argument("--price", type=int, choices=PRICES, required=True)
    run_parser.add_argument("--matrix", required=True)
    run_parser.add_argument("--matrix-file", type=Path, default=runner.MATRIX)
    run_parser.add_argument("--model", default=MODEL)
    run_parser.add_argument("--out", type=Path, default=RUNS)
    run_parser.add_argument("--resume", metavar="RUN_ID")
    spend_parser = subparsers.add_parser("spend")
    spend_parser.set_defaults(command="spend")
    args = parser.parse_args(argv)
    if args.command == "spend":
        print(f"{spend_usd():.4f}")
        return 0
    try:
        run_dir = run_arm(
            args.agent,
            args.price,
            args.matrix,
            args.out,
            matrix_file=args.matrix_file,
            model=args.model,
            run_id=args.resume,
            resume=bool(args.resume),
        )
    except (FileNotFoundError, ValueError, FileExistsError) as err:
        print(f"cost_driver: {err}", file=sys.stderr)
        return 2
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
