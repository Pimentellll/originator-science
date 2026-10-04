"""Evidence-only reading of a public trace (no truth, no reward)."""

from __future__ import annotations

from dataclasses import dataclass, field

from mirage.core import ActionType
from mirage.evaluation.campaign.config import EvaluatorConfig
from mirage.provenance.compat import (
    MEASUREMENT_ACTIONS,
    measurements_of,
    quality_of,
)
from mirage.provenance.events import EpisodeRecord, ScientificEvent

# Failure marginal -> the assay that directly informs it.
FACTOR_ASSAY: dict[str, ActionType] = {
    "p_folding_failure": ActionType.MEASURE_STABILITY,
    "p_aggregation_failure": ActionType.MEASURE_SEC,
    "p_affinity_failure": ActionType.MEASURE_SPR,
    "p_kinetic_failure": ActionType.MEASURE_SPR,
    "p_epitope_failure": ActionType.MEASURE_EPITOPE,
    "p_developability_failure": ActionType.MEASURE_DEVELOPABILITY,
}
MOLECULAR_MARGINALS = tuple(FACTOR_ASSAY)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Ledger:
    """Index over measurement events of one record."""

    config: EvaluatorConfig
    events: list[ScientificEvent] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: EpisodeRecord, config: EvaluatorConfig) -> Ledger:
        return cls(config, [e for e in record.events if e.action.action_type in MEASUREMENT_ACTIONS])

    def degraded(self, event: ScientificEvent) -> bool:
        label = quality_of(event.observation)
        return any(marker in label for marker in self.config.degraded_quality_markers)

    def observed(self, candidate_id: str | None, action: ActionType) -> list[ScientificEvent]:
        """Measurement events with a result, for one candidate (None = any candidate)."""
        return [
            e
            for e in self.events
            if e.action.action_type == action
            and e.observation is not None
            and (candidate_id is None or e.candidate_id == candidate_id)
        ]

    def clean(self, candidate_id: str | None, action: ActionType) -> list[ScientificEvent]:
        return [e for e in self.observed(candidate_id, action) if not self.degraded(e)]

    def assay_validation_passed(self) -> bool:
        threshold = self.config.control_pass_threshold
        return any(
            measurements_of(e.observation).get("control_signal", float("-inf")) >= threshold
            for e in self.clean(None, ActionType.VALIDATE_ASSAY)
        )

    def assay_validation_run(self) -> bool:
        return bool(self.observed(None, ActionType.VALIDATE_ASSAY))

    def orthogonal_function_present(self) -> bool:
        threshold = self.config.orthogonal_pass_threshold
        return any(
            measurements_of(e.observation).get("orthogonal_function_signal", float("-inf"))
            >= threshold
            for e in self.clean(None, ActionType.ORTHOGONAL_FUNCTION)
        )

    def performed_actions(self, candidate_id: str) -> set[ActionType]:
        return {e.action.action_type for e in self.events if e.candidate_id == candidate_id and e.observation is not None}

    def has_functional_evidence(self, candidate_id: str) -> bool:
        functional = set(self.config.functional_actions)
        on_candidate = self.performed_actions(candidate_id)
        if on_candidate & (functional - {ActionType.ORTHOGONAL_FUNCTION}):
            return True
        return bool(self.observed(None, ActionType.ORTHOGONAL_FUNCTION))


def _marginal(belief: dict | None, name: str) -> float | None:
    return None if belief is None else float(belief[name])


def supports_select(ledger: Ledger, cand: str, belief: dict | None) -> list[Check]:
    cfg = ledger.config
    checks = [
        Check(
            f"ran_{a.value.lower()}",
            bool(ledger.observed(cand, a)),
            "required before a justified SELECT",
        )
        for a in cfg.select_required_actions
    ]
    if ActionType.MEASURE_SPR in cfg.select_required_actions:
        checks.append(Check("spr_readout_reliable", bool(ledger.clean(cand, ActionType.MEASURE_SPR))))
    if cfg.select_requires_assay_validation:
        checks.append(Check("assay_validated", ledger.assay_validation_passed(), "VALIDATE_ASSAY control passed"))
    if belief is None:
        checks.append(Check("belief_supports_select", False, "no belief recorded at decision"))
    else:
        worst = max(float(belief[m]) for m in (*MOLECULAR_MARGINALS, "p_assay_invalid", "p_model_invalid"))
        checks.append(Check("belief_supports_select", worst <= cfg.support_max_marginal, f"max failure marginal {worst:.3f}"))
    return checks


def supports_reject(ledger: Ledger, cand: str, belief: dict | None) -> list[Check]:
    cfg = ledger.config
    if belief is None:
        return [Check("belief_supports_reject", False, "no belief recorded at decision")]
    supported = [
        m
        for m in MOLECULAR_MARGINALS
        if float(belief[m]) >= cfg.support_min_marginal
        and ledger.clean(cand, FACTOR_ASSAY[m])
    ]
    return [
        Check("failure_evidenced", bool(supported), f"likely and directly assayed: {supported}"),
        Check(
            "assay_not_in_doubt",
            ledger.assay_validation_passed() or float(belief["p_assay_invalid"]) <= cfg.support_max_marginal,
            "assay validated or believed valid",
        ),
    ]


def supports_model_invalid(ledger: Ledger, cand: str, belief: dict | None) -> list[Check]:
    cfg = ledger.config
    direct = bool(ledger.clean(cand, ActionType.MEASURE_SPR) or ledger.observed(cand, ActionType.MEASURE_EPITOPE))
    ortho = bool(ledger.observed(None, ActionType.ORTHOGONAL_FUNCTION))
    checks = [
        Check("assay_validated", ledger.assay_validation_passed(), "valid assay/control required"),
        Check("target_evidence", direct or ortho, "direct (SPR/epitope) or orthogonal evidence"),
    ]
    if belief is None:
        checks.append(Check("belief_supports_model_invalid", False, "no belief recorded at decision"))
    else:
        ok = (
            float(belief["p_model_invalid"]) >= cfg.support_min_marginal
            and float(belief["p_assay_invalid"]) <= cfg.support_max_marginal
        )
        checks.append(Check("belief_supports_model_invalid", ok, f"p_model_invalid={belief['p_model_invalid']:.3f}"))
    return checks


def supports_abstain(
    ledger: Ledger, cand: str, belief: dict | None, *, exhausted: bool
) -> list[Check]:
    """Abstention is justified when no committal decision is evidence-supported, or the
    campaign has run out of resources to improve the evidence."""
    committal = {
        "SELECT": supports_select(ledger, cand, belief),
        "REJECT": supports_reject(ledger, cand, belief),
        "MODEL_INVALID": supports_model_invalid(ledger, cand, belief),
    }
    already = [name for name, checks in committal.items() if all(c.passed for c in checks)]
    return [
        Check(
            "no_committal_decision_supported",
            not already or exhausted,
            f"supported alternatives: {already}; exhausted={exhausted}",
        )
    ]
