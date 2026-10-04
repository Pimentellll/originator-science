"""Derived failure-locus view of the factorised posterior.

MOLECULE FAILURE (folding, aggregation, affinity, kinetics, epitope, developability),
EXPERIMENT FAILURE (assay invalid) and BIOLOGICAL HYPOTHESIS FAILURE (model invalid)
are computed directly from the weighted particles. The molecule probability is the
posterior mass of the UNION of the six molecular rules, so overlapping mechanisms are
counted once; it is bounded by max(mechanism) <= p_molecule <= min(1, sum(mechanisms)).
This is a view over the posterior, not a replacement for BeliefSummary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mirage.belief.schema import EXPERIMENT_FIELD, FAILURE_FIELDS, MODEL_FIELD, MOLECULAR_FIELDS

if TYPE_CHECKING:
    from mirage.belief.particles import ParticleBelief

LOCUS_LABELS = ("none", "molecule", "experiment", "molecule+experiment", "model", "molecule+model", "experiment+model", "molecule+experiment+model")
_EPS = 1e-9


class FailureLocalisation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    p_molecule_failure: float = Field(ge=0.0, le=1.0)
    p_experiment_failure: float = Field(ge=0.0, le=1.0)
    p_model_failure: float = Field(ge=0.0, le=1.0)
    p_no_failure: float = Field(ge=0.0, le=1.0)
    p_compound_molecule_failure: float = Field(ge=0.0, le=1.0)  # two or more molecular mechanisms
    mechanism_probabilities: dict[str, float]
    # Exhaustive, mutually exclusive posterior over which loci are failing (sums to 1).
    locus_joint: dict[str, float]
    leading_locus: Literal["none", "molecule", "experiment", "model"]

    @model_validator(mode="after")
    def _consistent(self) -> "FailureLocalisation":
        mols = [self.mechanism_probabilities[f] for f in MOLECULAR_FIELDS]
        if not (max(mols) - _EPS <= self.p_molecule_failure <= min(1.0, sum(mols)) + _EPS):
            raise ValueError("p_molecule_failure must lie between the max and the (capped) sum of its mechanisms")
        if abs(sum(self.locus_joint.values()) - 1.0) > 1e-6:
            raise ValueError("locus_joint must sum to 1")
        return self

    @classmethod
    def from_belief(cls, belief: "ParticleBelief") -> "FailureLocalisation":
        w = belief.weights
        ind = belief.failure_indicators()
        mol_any = ind[:, : len(MOLECULAR_FIELDS)].any(axis=1)
        exp, mod = ind[:, FAILURE_FIELDS.index(EXPERIMENT_FIELD)], ind[:, FAILURE_FIELDS.index(MODEL_FIELD)]
        locus = mol_any.astype(int) + 2 * exp.astype(int) + 4 * mod.astype(int)
        joint = np.bincount(locus, weights=w, minlength=8)
        mech = belief.failure_probabilities()
        p_mol, p_exp, p_mod = float(w @ mol_any), float(w @ exp), float(w @ mod)
        clip = lambda x: float(min(1.0, max(0.0, x)))  # noqa: E731
        leading = {"molecule": p_mol, "experiment": p_exp, "model": p_mod}
        none = float(joint[0])
        top = max(leading, key=leading.get)
        return cls(
            p_molecule_failure=clip(p_mol),
            p_experiment_failure=clip(p_exp),
            p_model_failure=clip(p_mod),
            p_no_failure=clip(none),
            p_compound_molecule_failure=clip(float(w @ (ind[:, : len(MOLECULAR_FIELDS)].sum(axis=1) >= 2))),
            mechanism_probabilities=mech,
            locus_joint={label: clip(float(joint[i])) for i, label in enumerate(LOCUS_LABELS)},
            leading_locus="none" if none >= leading[top] else top,
        )
