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


def _passive_by_time(session: LabSession) -> dict[int, float]:
    return {m.time_h: m.mean_reading for m in session.observation().passive_readings}


class GoodScientist:
    """DESIGN §16.1: one 1:10 late measurement (3 replicates) and the R ≥ τ rule."""

    name = "GoodScientist"

    def run(self, session: LabSession) -> None:
        session.call("declare_state", {"notes": GOOD_SCIENTIST_NOTES, "p_growth_continued": 0.5})
        passive = _passive_by_time(session)
        p_hat = float(np.mean([passive[t] for t in PLATEAU_TIMES_H]))
        res = session.call("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 3})
        if not res.ok or res.result is None:
            raise RuntimeError(f"GoodScientist measurement rejected: {res.error}")
        c_hat = 10.0 * float(np.mean(res.result["readings"]))
        ratio = c_hat / p_hat
        continued = ratio >= TAU
        session.call("submit_diagnosis", {
            "diagnosis": "GROWTH_CONTINUED" if continued else "GROWTH_STOPPED",
            "p_growth_continued": 0.99 if continued else 0.01,
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
        session.call("submit_diagnosis", {
            "diagnosis": label,
            "p_growth_continued": p,
            "late_biomass_estimate_od": None,
            "rationale": "Late passive mean (13-18 h) under the scenario-prior reference densities.",
        })
