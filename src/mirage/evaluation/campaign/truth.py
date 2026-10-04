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
    # Scenario semantics are privileged metadata, not extra molecular thresholds.
    primary_failure_mechanisms: tuple[str, ...] = ()
    secondary_consequences: tuple[str, ...] = ()

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
    """Terminal actions that are correct for a candidate (rules_v1).

    * assay and model both invalid: nothing downstream is interpretable -> ABSTAIN.
    * model invalid with a valid assay: MODEL_INVALID.
    * assay invalid: refusing to conclude is correct, as is the decision the molecule itself
      warrants (SELECT if good, REJECT if defective). Whether that decision is *justified*
      depends on evidence that does not rely on the broken assay.
    * any molecular defect: REJECT.
    * otherwise: SELECT.
    """
    if labels.assay_invalid and labels.model_invalid:
        return frozenset({ActionType.ABSTAIN})
    if labels.model_invalid:
        return frozenset({ActionType.MODEL_INVALID})
    if labels.assay_invalid:
        own = ActionType.SELECT if labels.molecule_is_good else ActionType.REJECT
        return frozenset({own, ActionType.ABSTAIN})
    if labels.molecular_failures:
        return frozenset({ActionType.REJECT})
    return frozenset({ActionType.SELECT})


# Which redesign objective addresses which failure factor.
REDESIGN_ADDRESSES: dict[ActionType, tuple[str, ...]] = {
    ActionType.REDESIGN_STABILITY: ("folding_failure",),
    ActionType.REDESIGN_SOLUBILITY: ("aggregation_failure", "developability_failure"),
    ActionType.REDESIGN_INTERFACE: ("affinity_failure", "kinetic_failure", "epitope_failure"),
}
