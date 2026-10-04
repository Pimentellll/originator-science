"""Adversarial scripted agents for the grader red-team (see REGISTRATION.md).

Every agent sees only the visible ``LabSession``. None of them is a benchmark baseline.
"""

from __future__ import annotations

from mirage.agents.base import LabSession
from mirage.agents.scripted import (
    PLATEAU_TIMES_H,
    TAU,
    GoodScientist,
    PassiveBayesAgent,
    PassiveClassifier,
    _call,
    _passive_by_time,
)

ABOVE, AS_READ = "BIOMASS_ABOVE_READING", "BIOMASS_AS_READ"
TOKEN_CONTROL = {"time_h": 18, "dilution_factor": 10.0, "replicates": 1}
GS_CONTROL = {"time_h": 18, "dilution_factor": 10.0, "replicates": 3}
NONDIAG_SPEND = (
    {"time_h": 18, "dilution_factor": 1.0, "replicates": 3},
    {"time_h": 6, "dilution_factor": 10.0, "replicates": 3},
)
EDGE_CONTROL = {"time_h": 12, "dilution_factor": 1.1, "replicates": 1}
ABSURD_ESTIMATE = 1000.0


def plateau_mean(session: LabSession) -> float:
    passive = _passive_by_time(session)
    return sum(passive[t] for t in PLATEAU_TIMES_H) / len(PLATEAU_TIMES_H)


def passive_label(
    session: LabSession, classifier: PassiveClassifier
) -> tuple[str, float]:
    passive = _passive_by_time(session)
    return classifier.classify([passive[t] for t in sorted(passive)])


def corrected_ratio(session: LabSession, result: dict) -> float:
    """R = d * mean(readings) / mean(passive 15-18 h), from what the agent saw."""
    readings = result["readings"]
    return (
        result["dilution_factor"]
        * (sum(readings) / len(readings))
        / plateau_mean(session)
    )


def _submit(
    session: LabSession,
    name: str,
    label: str,
    p: float,
    estimate: float | None,
    rationale: str,
) -> None:
    _call(
        session,
        name,
        "submit_diagnosis",
        {
            "diagnosis": label,
            "p_biomass_above_reading": float(p),
            "late_biomass_estimate_od": estimate,
            "rationale": rationale,
        },
    )


class TokenFixed:
    """One 1-unit diagnostic control, result ignored, fixed label."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.name = "adv_token_above" if label == ABOVE else "adv_token_asread"

    def run(self, session: LabSession) -> None:
        _call(session, self.name, "measure_od", TOKEN_CONTROL)
        _submit(
            session,
            self.name,
            self.label,
            0.99 if self.label == ABOVE else 0.01,
            None,
            "Fixed answer.",
        )


class TokenPassive:
    """One 1-unit diagnostic control, result ignored, PassiveBayes answer."""

    name = "adv_token_passive"

    def __init__(self, classifier: PassiveClassifier) -> None:
        self._classifier = classifier

    def run(self, session: LabSession) -> None:
        _call(session, self.name, "measure_od", TOKEN_CONTROL)
        label, p = passive_label(session, self._classifier)
        _submit(session, self.name, label, p, None, "Passive classifier answer.")


class GSVariant:
    """GoodScientist's protocol and R >= TAU rule, with one output manipulated."""

    def __init__(self, name: str) -> None:
        if name not in (
            "adv_contrarian",
            "adv_absurd_estimate",
            "adv_p_mismatch",
            "adv_hedge",
        ):
            raise ValueError(name)
        self.name = name

    def run(self, session: LabSession) -> None:
        res = _call(session, self.name, "measure_od", GS_CONTROL)
        r = corrected_ratio(session, res)
        estimate = 10.0 * sum(res["readings"]) / len(res["readings"])
        above = r >= TAU
        p = 0.99 if above else 0.01
        if self.name == "adv_contrarian":
            above, p = not above, 1.0 - p
        elif self.name == "adv_absurd_estimate":
            estimate = ABSURD_ESTIMATE
        elif self.name == "adv_p_mismatch":
            p = 1.0 - p
        elif self.name == "adv_hedge":
            p = 0.5
        _submit(
            session,
            self.name,
            ABOVE if above else AS_READ,
            p,
            estimate,
            f"R = {r:.3f}.",
        )


class NonDiagnosticSpend:
    """Whole budget on non-diagnostic measurements, then PassiveBayes answer."""

    name = "adv_nondiag_spend"

    def __init__(self, classifier: PassiveClassifier) -> None:
        self._classifier = classifier

    def run(self, session: LabSession) -> None:
        for req in NONDIAG_SPEND:
            _call(session, self.name, "measure_od", req)
        label, p = passive_label(session, self._classifier)
        _submit(session, self.name, label, p, None, "Passive classifier answer.")


class ExtremePassive:
    """PassiveBayes label with a hard 0/1 probability."""

    name = "adv_extreme_passive"

    def __init__(self, classifier: PassiveClassifier) -> None:
        self._classifier = classifier

    def run(self, session: LabSession) -> None:
        label, _ = passive_label(session, self._classifier)
        _submit(
            session,
            self.name,
            label,
            1.0 if label == ABOVE else 0.0,
            None,
            "Passive classifier answer, hard probability.",
        )


class EdgeHonest:
    """Weakest D_diag action (12 h, 1:1.1, 1 rep) with the per-d evidence threshold."""

    name = "probe_edge_honest"

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold

    def run(self, session: LabSession) -> None:
        res = _call(session, self.name, "measure_od", EDGE_CONTROL)
        r = corrected_ratio(session, res)
        above = r >= self.threshold
        _submit(
            session,
            self.name,
            ABOVE if above else AS_READ,
            0.99 if above else 0.01,
            None,
            f"R = {r:.4f} vs tau(1.1) = {self.threshold:.4f}.",
        )


def make_agents(
    classifier: PassiveClassifier, edge_threshold: float
) -> dict[str, object]:
    """All registered agents keyed by their REGISTRATION.md id."""
    gs, pb = GoodScientist(), PassiveBayesAgent(classifier)
    agents = {
        "ref_good_scientist": gs,
        "ref_passive_bayes": pb,
        "adv_token_above": TokenFixed(ABOVE),
        "adv_token_asread": TokenFixed(AS_READ),
        "adv_token_passive": TokenPassive(classifier),
        "adv_contrarian": GSVariant("adv_contrarian"),
        "adv_nondiag_spend": NonDiagnosticSpend(classifier),
        "adv_absurd_estimate": GSVariant("adv_absurd_estimate"),
        "adv_p_mismatch": GSVariant("adv_p_mismatch"),
        "adv_extreme_passive": ExtremePassive(classifier),
        "adv_hedge": GSVariant("adv_hedge"),
        "probe_edge_honest": EdgeHonest(edge_threshold),
    }
    return agents
