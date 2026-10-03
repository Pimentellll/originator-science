"""HIDDEN: the simulated lab for one episode (DESIGN §7, §8, §11, §14, §18, §19).

Holds the hidden ``EpisodeConfig``. Agents only ever receive the ``LabSession`` facade
returned by :meth:`LabEnvironment.session`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, get_args

import numpy as np
from pydantic import ValidationError

from mirage.assay.od_reader import read, response
from mirage.biology.growth import richards
from mirage.config import EpisodeConfig
from mirage.evaluation.metrics import EpisodeStatus, EventRecord
from mirage.lab.tools import (
    BUDGET_UNITS,
    MAX_TIME_H,
    MAX_TURNS,
    AgentState,
    Diagnosis,
    MeasurementRequest,
    MeasurementResult,
    Observation,
    ToolResponse,
    render_measurement,
)

PASSIVE_STREAM = 1
MEASUREMENT_STREAM = 2
STATUSES = frozenset(get_args(EpisodeStatus))


@dataclass(frozen=True)
class AcceptedMeasurement:
    """Hidden bookkeeping for one accepted ``measure_od`` (noise-free values for the audit)."""

    event_index: int
    request_index: int
    time_h: int
    dilution_factor: float
    replicates: int
    latent_biomass_odeq: float
    presented_biomass_odeq: float
    noise_free_reading: float


def _one_line(err: ValidationError) -> str:
    parts = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"]) or "arguments"
        parts.append(f"{loc}: {e['msg']}")
    return "; ".join(parts)


class LabEnvironment:
    """One episode: passive history, validated measurements, budget, turns, event log."""

    def __init__(self, config: EpisodeConfig, *, max_turns: int = MAX_TURNS) -> None:
        if type(max_turns) is not int or max_turns < 1:
            raise ValueError(f"max_turns must be a positive integer, got {max_turns!r}")
        self.config = config
        self.max_turns = max_turns
        self.budget_total = BUDGET_UNITS
        self.budget_remaining = BUDGET_UNITS
        self.turn = 0
        self.events: list[EventRecord] = []
        self.accepted: list[AcceptedMeasurement] = []
        self.measurements: list[MeasurementResult] = []
        self.agent_states: list[AgentState] = []
        self.diagnosis: Diagnosis | None = None
        self.status: EpisodeStatus | None = None
        self.passive = self._passive_history()

    # ---- hidden-side helpers -------------------------------------------------

    def latent(self, time_h: int | float) -> float:
        """Noise-free latent biomass X(t) in ODeq."""
        return float(richards(time_h, **self.config.growth.model_dump()))

    def _assay_kwargs(self) -> dict[str, float]:
        a = self.config.assay
        return dict(s_odeq=a.s_odeq, n=a.n, sigma_abs=a.sigma_abs, sigma_rel=a.sigma_rel)

    def _stream(self, *key: int) -> np.random.Generator:
        return np.random.default_rng(np.random.SeedSequence([self.config.seed, *key]))

    def _passive_history(self) -> list[MeasurementResult]:
        t = np.arange(MAX_TIME_H + 1)
        x = richards(t, **self.config.growth.model_dump())
        ys = read(x, self._stream(PASSIVE_STREAM), **self._assay_kwargs())
        return [
            MeasurementResult(
                source="passive",
                request_index=None,
                time_h=int(ti),
                dilution_factor=1.0,
                readings=[float(y)],
                mean_reading=float(y),
                cost_units=0,
                budget_remaining=self.budget_total,
            )
            for ti, y in zip(t, ys, strict=True)
        ]

    def finish(self, status: EpisodeStatus) -> None:
        """End the episode with ``status`` (the runner uses this for API_FAILURE / REFUSED).

        Terminal statuses are final: finishing an already finished episode raises, so
        callers must check ``finished`` first (e.g. after the turn limit or a diagnosis).
        """
        if status not in STATUSES:
            raise ValueError(f"invalid episode status: {status!r}")
        if self.status is not None:
            raise RuntimeError(f"episode already finished with {self.status}; cannot set {status}")
        if status == "DIAGNOSED" and self.diagnosis is None:
            raise ValueError("DIAGNOSED requires an accepted diagnosis")
        self.status = status

    @property
    def finished(self) -> bool:
        return self.status is not None

    def observation(self) -> Observation:
        return Observation(
            passive_readings=self.passive,
            budget_total=self.budget_total,
            budget_remaining=self.budget_remaining,
        )

    # ---- tool dispatch -------------------------------------------------------

    def call(self, tool: str, args: dict[str, Any]) -> ToolResponse:
        """Execute one tool call. Every call, valid or not, is one turn and one event."""
        if self.finished:
            raise RuntimeError("episode is finished; no further tool calls are accepted")
        self.turn += 1
        index = len(self.events)
        if not isinstance(args, dict):
            result, error = None, "arguments must be a JSON object"
        elif tool == "measure_od":
            result, error = self._measure(index, args)
        elif tool == "declare_state":
            result, error = self._declare(args)
        elif tool == "submit_diagnosis":
            result, error = self._diagnose(args)
        else:
            result, error = None, f"unknown tool: {tool}"
        self.events.append(
            EventRecord(
                index=index,
                turn=self.turn,
                tool=tool,
                arguments=dict(args) if isinstance(args, dict) else {"_raw": repr(args)},
                ok=error is None,
                result=result,
                error=error,
            )
        )
        if not self.finished and self.turn >= self.max_turns:
            self.finish("NO_DIAGNOSIS")
        return ToolResponse(ok=error is None, result=result, error=error)

    def _measure(self, index: int, args: dict[str, Any]) -> tuple[dict | None, str | None]:
        try:
            req = MeasurementRequest(**args)
        except ValidationError as err:
            return None, _one_line(err)
        if req.replicates > self.budget_remaining:
            return None, (
                f"replicates ({req.replicates}) exceeds remaining budget ({self.budget_remaining})"
            )
        request_index = len(self.accepted)
        x = self.latent(req.time_h)
        presented = x / req.dilution_factor
        rng = self._stream(MEASUREMENT_STREAM, request_index)
        readings = read(np.full(req.replicates, presented), rng, **self._assay_kwargs())
        a = self.config.assay
        noise_free = float(response(presented, s_odeq=a.s_odeq, n=a.n))
        self.budget_remaining -= req.replicates
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
            cost_units=req.replicates,
            budget_remaining=self.budget_remaining,
        )
        self.measurements.append(res)
        return render_measurement(res), None

    def _declare(self, args: dict[str, Any]) -> tuple[dict | None, str | None]:
        try:
            self.agent_states.append(AgentState(**args))
        except ValidationError as err:
            return None, _one_line(err)
        return {"status": "recorded"}, None

    def _diagnose(self, args: dict[str, Any]) -> tuple[dict | None, str | None]:
        try:
            self.diagnosis = Diagnosis(**args)
        except ValidationError as err:
            return None, _one_line(err)
        self.finish("DIAGNOSED")
        return {"status": "received"}, None

    def session(self) -> _Session:
        """The visible facade handed to the agent (DESIGN §12)."""
        return _Session(self)


class _Session:
    """Implements ``mirage.agents.base.LabSession``; exposes no hidden attribute by name."""

    __slots__ = ("_observation", "_call", "_finished")

    def __init__(self, env: LabEnvironment) -> None:
        self._observation = env.observation
        self._call = env.call
        self._finished = lambda: env.finished

    def observation(self) -> Observation:
        return self._observation()

    def call(self, tool: str, args: dict[str, Any]) -> ToolResponse:
        return self._call(tool, args)

    @property
    def finished(self) -> bool:
        return self._finished()
