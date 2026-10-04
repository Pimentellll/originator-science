"""Offline run-data and sandbox APIs for the local web console."""

from __future__ import annotations

import json
import math
import random
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from mirage import __version__
from mirage.assay.od_reader import response
from mirage.biology.conditions import Condition
from mirage.biology.growth import richards
from mirage.config import EpisodeConfig, load_demo_pair, load_prior, sample_episode
from mirage.evaluation import runner
from mirage.evaluation.metrics import EpisodeResult, audit_measurements, score_episode
from mirage.lab.environment import LabEnvironment
from mirage.lab.tools import MeasurementRequest


class APIError(Exception):
    """An error with an HTTP status suitable for the local JSON API."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


def health() -> dict[str, Any]:
    return {"ok": True, "version": __version__, "offline": True}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _discover_runs(
    results_root: str | Path,
) -> list[tuple[Path, dict[str, Any], str]]:
    root = Path(results_root).resolve()
    found: list[tuple[Path, dict[str, Any], str]] = []
    seen: set[str] = set()
    if not root.exists():
        return found

    for manifest_path in sorted(root.rglob("manifest.json")):
        relative = manifest_path.relative_to(root)
        if "gate0" in relative.parts:
            continue
        run_dir = manifest_path.parent
        episodes_dir = run_dir / "episodes"
        if not episodes_dir.is_dir():
            continue
        run_id = run_dir.name
        if run_id in seen:
            raise ValueError(f"duplicate run_id {run_id!r} under {root}")
        seen.add(run_id)
        group = str(run_dir.parent.relative_to(root))
        found.append((run_dir, _load_json(manifest_path), "" if group == "." else group))
    return found


def _episode_records(run_dir: Path) -> list[dict[str, Any]]:
    return [
        _load_json(path)
        for path in sorted((run_dir / "episodes").glob("*.json"))
        if path.is_file()
    ]


def _headline(summary: dict[str, Any], episode_count: int) -> dict[str, Any]:
    overall = summary["metrics"]["intention_to_treat"]["overall"]
    n = overall.get("n", episode_count)
    headline: dict[str, Any] = {
        name: {
            "k": overall[name]["k"],
            "n": n,
            "rate": overall[name]["rate"],
            "wilson95": overall[name]["wilson95"],
        }
        for name in ("M1", "M2", "M3")
    }
    headline["Q1"] = overall.get("Q1")
    return headline


def _run_entry(
    run_dir: Path, manifest: dict[str, Any], group: str
) -> dict[str, Any]:
    records = _episode_records(run_dir)
    episode_count = manifest.get("n_episodes", len(records))
    summary_path = run_dir / "summary.json"
    summary = _load_json(summary_path) if summary_path.is_file() else None
    briers = [
        record["scores"]["brier"]
        for record in records
        if record.get("scores", {}).get("brier") is not None
    ]
    return {
        "run_id": run_dir.name,
        "group": group,
        "agent": manifest.get("agent"),
        "model": manifest.get("model"),
        "effort": manifest.get("effort"),
        "prompt_version": manifest.get("prompt_version"),
        "matrix": manifest.get("matrix"),
        "n_episodes": episode_count,
        "frozen": (run_dir / "FREEZE.md").is_file(),
        "headline": None if summary is None else _headline(summary, episode_count),
        "brier_mean": math.fsum(briers) / len(briers) if briers else None,
    }


def list_runs(results_root: str | Path) -> list[dict[str, Any]]:
    entries = [
        _run_entry(run_dir, manifest, group)
        for run_dir, manifest, group in _discover_runs(results_root)
    ]
    return sorted(entries, key=lambda entry: (entry["group"], entry["run_id"]))


def list_exploratory_runs(
    exploratory_root: str | Path,
) -> list[dict[str, Any]]:
    root = Path(exploratory_root)
    index_path = root / "index.json"
    if not root.is_dir() or not index_path.is_file():
        return []

    registry = _load_json(index_path)
    entries = []
    for registered in registry.get("runs", []):
        experiment = registered["experiment"]
        run_id = registered["run"]
        run_dir = root / experiment / "runs" / run_id
        manifest_path = run_dir / "manifest.json"
        if not run_dir.is_dir() or not manifest_path.is_file():
            raise APIError(
                500,
                f"registered exploratory run is missing: {experiment}/{run_id}",
            )

        manifest = _load_json(manifest_path)
        summary_path = run_dir / "summary.json"
        summary = _load_json(summary_path) if summary_path.is_file() else {}
        overall = (
            summary.get("metrics", {})
            .get("intention_to_treat", {})
            .get("overall", {})
        )
        entry = _run_entry(run_dir, manifest, group="exploratory")
        entry.update(
            {
                "label": registered["label"],
                "variable": registered["variable"],
                "experiment": experiment,
                "result_path": f"experiments/exploratory/{experiment}/RESULT.md",
                "units_mean": overall.get("M4", {}).get("mean"),
            }
        )
        entries.append(entry)
    return entries


def _find_run(results_root: str | Path, run_id: str) -> tuple[Path, dict[str, Any], str]:
    for run_dir, manifest, group in _discover_runs(results_root):
        if run_dir.name == run_id:
            return run_dir, manifest, group
    raise APIError(404, "unknown run")


def get_run(results_root: str | Path, run_id: str) -> dict[str, Any]:
    run_dir, manifest, group = _find_run(results_root, run_id)
    summary_path = run_dir / "summary.json"
    episodes = []
    for record in _episode_records(run_dir):
        episode = record["episode"]
        diagnosis = record.get("diagnosis") or {}
        episodes.append(
            {
                "episode_id": episode["episode_id"],
                "condition": episode["condition"],
                "seed": episode["seed"],
                "status": record["status"],
                "diagnosis": diagnosis.get("diagnosis"),
                "p_biomass_above_reading": diagnosis.get("p_biomass_above_reading"),
                "late_biomass_estimate_od": diagnosis.get("late_biomass_estimate_od"),
                "scores": record["scores"],
            }
        )
    return {
        "run": _run_entry(run_dir, manifest, group),
        "manifest": manifest,
        "summary": _load_json(summary_path) if summary_path.is_file() else None,
        "episodes": episodes,
    }


def _curves(cfg: EpisodeConfig) -> dict[str, list[list[float]]]:
    times = [round(index / 10, 1) for index in range(181)]
    latent = richards(times, **cfg.growth.model_dump())
    readings = response(latent, s_odeq=cfg.assay.s_odeq, n=cfg.assay.n)
    return {
        "latent_curve": [
            [time, float(value)] for time, value in zip(times, latent, strict=True)
        ],
        "reading_curve": [
            [time, float(value)] for time, value in zip(times, readings, strict=True)
        ],
    }


def _derived(cfg: EpisodeConfig, record: EpisodeResult) -> dict[str, Any]:
    curves = _curves(cfg)
    measurements = []
    for event in record.events:
        if event.tool != "measure_od":
            continue
        try:
            request = MeasurementRequest.model_validate(event.arguments)
            time_h = request.time_h
            dilution_factor = request.dilution_factor
            replicates = request.replicates
        except ValidationError:
            time_h = event.arguments.get("time_h")
            dilution_factor = event.arguments.get("dilution_factor")
            replicates = event.arguments.get("replicates")
        result = event.result or {}
        mean_reading = result.get("mean_reading") if event.ok else None
        back_corrected = None
        if (
            isinstance(mean_reading, (int, float))
            and isinstance(dilution_factor, (int, float))
        ):
            back_corrected = mean_reading * dilution_factor
        measurements.append(
            {
                "event_index": event.index,
                "turn": event.turn,
                "time_h": time_h,
                "dilution_factor": dilution_factor,
                "replicates": replicates,
                "mean_reading": mean_reading,
                "back_corrected": back_corrected,
            }
        )
    return {
        **curves,
        "measurements": measurements,
    }


def get_episode(
    results_root: str | Path, run_id: str, episode_id: str
) -> dict[str, Any]:
    run_dir, _, _ = _find_run(results_root, run_id)
    if not episode_id or Path(episode_id).name != episode_id:
        raise APIError(404, "unknown episode")
    episode_path = run_dir / "episodes" / f"{episode_id}.json"
    if not episode_path.is_file():
        raise APIError(404, "unknown episode")
    raw = _load_json(episode_path)
    record = EpisodeResult.model_validate(raw)
    return {
        **raw,
        "derived": _derived(record.episode, record),
    }


def _column_order(column: dict[str, Any]) -> tuple[int, str]:
    agent, model = column["agent"], column["model"]
    if agent == "claude" and model == "claude-opus-5-5":
        rank = 0
    elif agent == "claude" and model == "claude-sonnet-5-5":
        rank = 1
    elif agent == "good_scientist":
        rank = 2
    elif agent == "passive_bayes":
        rank = 3
    else:
        rank = 4
    return rank, column["run_id"]


def get_grid(results_root: str | Path, matrix: str) -> dict[str, Any]:
    runs = [
        (run_dir, manifest, group)
        for run_dir, manifest, group in _discover_runs(results_root)
        if manifest.get("matrix") == matrix and manifest.get("matrix") != "demo"
    ]
    columns = sorted(
        [
            {
                "run_id": run_dir.name,
                "agent": manifest.get("agent"),
                "model": manifest.get("model"),
            }
            for run_dir, manifest, _ in runs
        ],
        key=_column_order,
    )
    run_by_id = {run_dir.name: run_dir for run_dir, _, _ in runs}
    rows_by_episode: dict[str, dict[str, Any]] = {}
    for column in columns:
        run_dir = run_by_id[column["run_id"]]
        for record in _episode_records(run_dir):
            episode = record["episode"]
            episode_id = episode["episode_id"]
            row = rows_by_episode.setdefault(
                episode_id,
                {
                    "episode_id": episode_id,
                    "seed": episode["seed"],
                    "condition": episode["condition"],
                    "cells": {},
                },
            )
            scores = record["scores"]
            row["cells"][column["run_id"]] = {
                "status": record["status"],
                "correct": scores["correct"],
                "justified": scores["justified"],
                "diagnostic_control": scores["diagnostic_control"],
            }
    rows = sorted(rows_by_episode.values(), key=lambda row: (row["seed"], row["episode_id"]))
    return {"columns": columns, "rows": rows}


def _reveal(cfg: EpisodeConfig) -> dict[str, Any]:
    curves = _curves(cfg)
    return {
        "condition": cfg.condition.value,
        "growth": cfg.growth.model_dump(mode="json"),
        "assay": cfg.assay.model_dump(mode="json"),
        "k_ratio": cfg.k_ratio,
        "latent_curve": curves["latent_curve"],
        "reading_curve": curves["reading_curve"],
    }


@dataclass
class _SandboxSession:
    config: EpisodeConfig
    env: LabEnvironment
    lock: threading.RLock = field(default_factory=threading.RLock)


class Sandbox:
    """Bounded in-memory store for interactive, unscored development episodes."""

    MAX_SESSIONS = 200

    def __init__(self) -> None:
        self._prior = load_prior(runner.SCENARIO)
        self._dset = runner.frozen_dset(self._prior, runner.GATE0_SUMMARY)
        matrices = _load_json(runner.MATRIX)["matrices"]
        self._evaluation_seeds = frozenset(
            seed
            for matrix_name in matrices
            for seed, _ in runner.load_matrix(runner.MATRIX, matrix_name)
        )
        self._sessions: OrderedDict[str, _SandboxSession] = OrderedDict()
        self._lock = threading.RLock()

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body, dict) or set(body) - {"seed", "condition", "preset"}:
            raise APIError(400, "expected seed, condition, and/or preset")
        preset = body.get("preset")
        if preset is not None:
            if preset not in ("demo-BP", "demo-MA"):
                raise APIError(400, "preset must be demo-BP or demo-MA")
            cfg = next(
                (
                    item
                    for item in load_demo_pair(
                        runner.DEMO, self._prior, seeds=runner.DEMO_SEEDS
                    )
                    if item.episode_id == preset
                ),
                None,
            )
            if cfg is None:
                raise APIError(400, "unknown demo preset")
        else:
            seed = body.get("seed")
            if seed is None:
                seed = random.randrange(0, 100_000)
            if type(seed) is not int or seed < 0:
                raise APIError(400, "seed must be a non-negative integer")
            if seed in self._evaluation_seeds:
                raise APIError(400, "seed belongs to an evaluation matrix")
            condition_value = body.get("condition")
            if condition_value is None:
                condition = random.choice(tuple(Condition))
            else:
                try:
                    condition = Condition(condition_value)
                except (TypeError, ValueError) as err:
                    raise APIError(400, "unknown condition") from err
            cfg = sample_episode(self._prior, seed, condition)

        env = LabEnvironment(cfg)
        session_id = uuid4().hex
        with self._lock:
            self._sessions[session_id] = _SandboxSession(cfg, env)
            while len(self._sessions) > self.MAX_SESSIONS:
                self._sessions.popitem(last=False)
        return {
            "session_id": session_id,
            "sandbox": True,
            "observation": env.observation().model_dump(mode="json"),
        }

    def _get_session(self, session_id: str) -> _SandboxSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise APIError(404, "unknown sandbox session")
        return session

    def measure(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        session = self._get_session(session_id)
        with session.lock:
            if session.env.finished:
                raise APIError(409, "sandbox session is finished")
            response_value = session.env.call("measure_od", body)
        return response_value.model_dump(mode="json")

    def submit(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        session = self._get_session(session_id)
        with session.lock:
            if session.env.finished:
                raise APIError(409, "sandbox session is finished")
            response_value = session.env.call("submit_diagnosis", body)
            if not response_value.ok:
                return response_value.model_dump(mode="json")
            return {
                "events": [event.model_dump(mode="json") for event in session.env.events],
                "diagnosis": session.env.diagnosis.model_dump(mode="json"),
                "status": session.env.status,
                "passive": [
                    measurement.model_dump(mode="json") for measurement in session.env.passive
                ],
            }

    def verdict(self, session_id: str) -> dict[str, Any]:
        session = self._get_session(session_id)
        with session.lock:
            if session.env.status != "DIAGNOSED":
                raise APIError(409, "diagnose the sandbox session first")
            cfg = session.config
            audit = audit_measurements(cfg, session.env.events, self._dset)
            scores = score_episode(cfg, session.env.events, session.env.diagnosis, audit)
            return {
                "episode": cfg.model_dump(mode="json"),
                "audit": [item.model_dump(mode="json") for item in audit],
                "scores": scores.model_dump(mode="json"),
                "reveal": _reveal(cfg),
            }

    def diagnose(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        public = self.submit(session_id, body)
        if public.get("ok") is False:
            return public
        verdict = self.verdict(session_id)
        return {
            "episode": verdict["episode"],
            **public,
            "audit": verdict["audit"],
            "scores": verdict["scores"],
            "reveal": verdict["reveal"],
        }

    def autoplay(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        session = self._get_session(session_id)
        with session.lock:
            if session.env.status != "DIAGNOSED":
                raise APIError(409, "diagnose the sandbox session before autoplay")
            if not isinstance(body, dict) or set(body) != {"agent"}:
                raise APIError(400, "agent is required")
            agent_name = body.get("agent")
            if agent_name not in ("good_scientist", "passive_bayes"):
                raise APIError(400, "agent must be good_scientist or passive_bayes")
            cfg = session.config
        agent = runner.make_agent(agent_name, self._prior)
        result = runner.run_episode(
            cfg, agent, self._dset, {"run_id": f"sandbox-{session_id}"}
        )
        return {**result.model_dump(mode="json"), "reveal": _reveal(cfg)}
