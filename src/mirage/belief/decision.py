"""Belief-side terminal semantics: what each terminal decision would be right about.

Benchmark-default semantics from the accepted evaluator rulings, expressed as an
exhaustive, mutually exclusive partition of latent worlds so a belief can compute the
probability that each terminal is correct:

    any molecular failure                          -> REJECT
    good molecule, model valid (assay either way)  -> SELECT
    good molecule, model invalid, assay valid      -> MODEL_INVALID
    good molecule, model invalid, assay invalid    -> ABSTAIN  (adversarial case)

This is the scientist's own approximation for planning and self-assessment. It is NOT
the evaluator: whether a terminal was scientifically *justified* is judged separately
from public evidence, and thresholds are versioned benchmark defaults.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mirage.belief.schema import EXPERIMENT_FIELD, FAILURE_FIELDS, MODEL_FIELD, MOLECULAR_FIELDS
from mirage.core.contracts import ActionType

TERMINAL_ORDER: tuple[ActionType, ...] = (
    ActionType.SELECT,
    ActionType.REJECT,
    ActionType.MODEL_INVALID,
    ActionType.ABSTAIN,
)


@dataclass(frozen=True)
class TerminalUtility:
    """Per-terminal utilities; benchmark defaults, not biological facts. Planners may lower
    ``correct_reject`` to value a rescued binder above a correctly diagnosed failure."""

    correct_select: float = 1.0
    correct_reject: float = 1.0
    correct_model_invalid: float = 1.0
    correct_abstain: float = 1.0
    wrong: float = -1.0
    abstain_unresolved: float = 0.0  # epistemic abstention when the world is not an abstain-world

    def correct(self) -> np.ndarray:
        return np.array([self.correct_select, self.correct_reject, self.correct_model_invalid, self.correct_abstain])


def correct_terminal_masks(indicators: np.ndarray) -> np.ndarray:
    """(n, 4) 0/1 matrix: column k = particle is a world where TERMINAL_ORDER[k] is correct."""
    mol = indicators[:, : len(MOLECULAR_FIELDS)].any(axis=1)
    assay_bad = indicators[:, FAILURE_FIELDS.index(EXPERIMENT_FIELD)]
    model_bad = indicators[:, FAILURE_FIELDS.index(MODEL_FIELD)]
    good = ~mol
    return np.column_stack([good & ~model_bad, mol, good & model_bad & ~assay_bad, good & model_bad & assay_bad]).astype(float)


def terminal_expected_utilities(
    weights: np.ndarray, masks: np.ndarray, utility: TerminalUtility = TerminalUtility()
) -> np.ndarray:
    """Expected utility of each terminal under weights ((n,) or (m, n)); returns (..., 4).

    Also usable for probabilities of being correct via ``weights @ masks``.
    """
    p = np.asarray(weights) @ masks
    eu = p * utility.correct() + (1.0 - p) * utility.wrong
    eu[..., 3] = p[..., 3] * utility.correct_abstain + (1.0 - p[..., 3]) * utility.abstain_unresolved
    return eu


def gated_terminal_utilities(
    weights: np.ndarray,
    masks: np.ndarray,
    assay_invalid: np.ndarray,
    utility: TerminalUtility = TerminalUtility(),
    *,
    diagnostic: bool,
    assay_tested: bool,
    assay_resolved: float = 0.10,
) -> np.ndarray:
    """Expected terminal utilities with the evidence gates both the planner and the
    justification certificate apply (disallowed terminals get -inf):

    * ABSTAIN needs at least one genuine diagnostic action (not justified at step zero);
    * SELECT and MODEL_INVALID need assay integrity established: the control has been run
      and p(assay invalid) <= ``assay_resolved``. A prior-driven or lucky positive claim is
      never recommended; when the assay is known broken and candidate function cannot be
      established independently, ABSTAIN is the supportable terminal.

    ``assay_invalid`` is the (n,) 0/1 indicator of the assay-invalid mechanism per particle.
    """
    eu = terminal_expected_utilities(weights, masks, utility).copy()
    if not diagnostic:
        eu[..., TERMINAL_ORDER.index(ActionType.ABSTAIN)] = -np.inf
    p_assay = np.asarray(weights) @ assay_invalid
    established = assay_tested & (p_assay <= assay_resolved)
    for t in (ActionType.SELECT, ActionType.MODEL_INVALID):
        col = TERMINAL_ORDER.index(t)
        eu[..., col] = np.where(established, eu[..., col], -np.inf)
    return eu
