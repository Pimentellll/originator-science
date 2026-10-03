"""Scripted baselines (DESIGN §16). They see only the visible ``LabSession``."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from mirage.agents.base import LabSession

TAU = 1.5
PLATEAU_TIMES_H = (15, 16, 17, 18)
GOOD_SCIENTIST_NOTES = (
    "Passive data alone cannot separate a real stop from readings that no longer track biomass."
)


class PassiveClassifier(Protocol):
    def classify(self, readings: list[float]) -> tuple[str, float]: ...


def _call(session: LabSession, agent: str, tool: str, args: dict) -> dict:
    """Make a tool call; any rejected call is a scripted-agent bug, so raise."""
    res = session.call(tool, args)
    if not res.ok or res.result is None:
        raise RuntimeError(f"{agent} {tool} rejected: {res.error}")
    return res.result


def _passive_by_time(session: LabSession) -> dict[int, float]:
    return {m.time_h: m.mean_reading for m in session.observation().passive_readings}


class GoodScientist:
    """DESIGN §16.1: one 1:10 late measurement (3 replicates) and the R ≥ τ rule."""

    name = "GoodScientist"

    def run(self, session: LabSession) -> None:
        _call(session, self.name, "declare_state",
              {"notes": GOOD_SCIENTIST_NOTES, "p_biomass_above_reading": 0.5})
        passive = _passive_by_time(session)
        p_hat = float(np.mean([passive[t] for t in PLATEAU_TIMES_H]))
        res = _call(session, self.name, "measure_od",
                    {"time_h": 18, "dilution_factor": 10.0, "replicates": 3})
        c_hat = 10.0 * float(np.mean(res["readings"]))
        ratio = c_hat / p_hat
        continued = ratio >= TAU
        _call(session, self.name, "submit_diagnosis", {
            "diagnosis": "BIOMASS_ABOVE_READING" if continued else "BIOMASS_AS_READ",
            "p_biomass_above_reading": 0.99 if continued else 0.01,
            "late_biomass_estimate_od": c_hat,
            "rationale": f"1:10 corrected late OD {c_hat:.4f} / passive plateau {p_hat:.4f} "
                         f"= {ratio:.3f} {'>=' if continued else '<'} {TAU}.",
        })


class PassiveBayesAgent:
    """DESIGN §16.2: passive data only; the classifier is injected by the runner."""

    name = "PassiveBayes"

    def __init__(self, classifier: PassiveClassifier) -> None:
        self._classifier = classifier

    def run(self, session: LabSession) -> None:
        passive = _passive_by_time(session)
        readings = [passive[t] for t in sorted(passive)]
        label, p = self._classifier.classify(readings)
        _call(session, self.name, "submit_diagnosis", {
            "diagnosis": label,
            "p_biomass_above_reading": p,
            "late_biomass_estimate_od": None,
            "rationale": "Late passive mean (13-18 h) under the scenario-prior reference densities.",
        })
