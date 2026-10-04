"""Privileged evaluator interface.

The evaluator receives ground-truth *failure labels*, never a public object. Environments
expose labels through an evaluator-specific accessor (TRUST_BOUNDARY.md); this module only
defines the shape the evaluator needs. Nothing here is importable by policies, the API
service layer or replay.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from mirage.core import ActionType


class FailureLabels(BaseModel):
    """Thresholded privileged state for one candidate. Factors are not exclusive."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    folding_failure: bool = False
    aggregation_failure: bool = False
    affinity_failure: bool = False
    kinetic_failure: bool = False
    epitope_failure: bool = False
    developability_failure: bool = False
    assay_invalid: bool = False
    model_invalid: bool = False

    @property
    def molecular_failures(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in (
                "folding_failure",
                "aggregation_failure",
                "affinity_failure",
                "kinetic_failure",
                "epitope_failure",
                "developability_failure",
            )
            if getattr(self, name)
        )

    @property
    def molecule_is_good(self) -> bool:
        return not self.molecular_failures


@runtime_checkable
class TruthOracle(Protocol):
    """Privileged accessor supplied by the environment owner to the evaluator only."""

    def failure_labels(self, candidate_id: str) -> FailureLabels: ...

    def scenario_class(self) -> str:
        """Generation/reporting archetype (SINGLE_FAILURE, ...); never policy-visible."""
        ...

    # Optional: ``regime() -> str`` ("myopic" | "path_dependent" | "invalid") for the
    # BASELINES requirement to report those world kinds separately. Read via getattr.


def correct_terminal_decisions(labels: FailureLabels) -> frozenset[ActionType]:
    """Truth-correct terminal actions for a candidate (frozen evaluator rulings, rules_v1).

    * assay AND model invalid: the canonical adversarial terminal is ABSTAIN. MODEL_INVALID
      states a true fact, so it is truth-correct too, but it is justified only if independent
      valid evidence specifically establishes model invalidity (the standard MODEL_INVALID
      support checks, which a broken assay control cannot satisfy).
    * model invalid, assay valid: MODEL_INVALID.
    * assay invalid (model valid): the disposition the molecule itself warrants (SELECT for a
      good molecule, REJECT for a defective one). ABSTAIN is *not* truth-correct, although it
      can be a justified abstention. SELECT is justified only with sufficient orthogonal support.
    * any molecular defect: REJECT.
    * otherwise: SELECT.
    """
    if labels.assay_invalid and labels.model_invalid:
        return frozenset({ActionType.ABSTAIN, ActionType.MODEL_INVALID})
    if labels.model_invalid:
        return frozenset({ActionType.MODEL_INVALID})
    if labels.assay_invalid:
        return frozenset({ActionType.SELECT if labels.molecule_is_good else ActionType.REJECT})
    if labels.molecular_failures:
        return frozenset({ActionType.REJECT})
    return frozenset({ActionType.SELECT})


# Which redesign objective addresses which failure factor.
REDESIGN_ADDRESSES: dict[ActionType, tuple[str, ...]] = {
    ActionType.REDESIGN_STABILITY: ("folding_failure",),
    ActionType.REDESIGN_SOLUBILITY: ("aggregation_failure", "developability_failure"),
    ActionType.REDESIGN_INTERFACE: ("affinity_failure", "kinetic_failure", "epitope_failure"),
}
