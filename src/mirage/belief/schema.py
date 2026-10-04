"""Latent-space schema for the factorised particle belief.

A particle is one plausible factorised latent scientific world: a row of named
continuous factors. Failure marginals are *not* a categorical class posterior;
each ``p_*_failure`` is the posterior mass of an independent threshold rule, so
several can be high at once (compound failure).

The rules and thresholds are modelling assumptions that must match the
environment's scenario/evaluator configuration. ``BINDER_SCHEMA_PROVISIONAL``
holds placeholder values until the environment publishes its canonical ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

import numpy as np

# Canonical BeliefSummary failure-marginal names, in a fixed order. The order
# defines the bit layout of the joint failure pattern used for entropy.
FAILURE_FIELDS: tuple[str, ...] = (
    "p_folding_failure",
    "p_aggregation_failure",
    "p_affinity_failure",
    "p_kinetic_failure",
    "p_epitope_failure",
    "p_developability_failure",
    "p_assay_invalid",
    "p_model_invalid",
)


# Hierarchy of failure loci. Columns 0-5 of the failure-indicator matrix are molecular
# mechanisms; the last two are the experiment (assay) and the biological hypothesis (model).
MOLECULAR_FIELDS: tuple[str, ...] = FAILURE_FIELDS[:6]
EXPERIMENT_FIELD = "p_assay_invalid"
MODEL_FIELD = "p_model_invalid"


@dataclass(frozen=True)
class FailureRule:
    """A particle is "failed" on a marginal when its factor crosses a threshold."""

    factor: str
    direction: Literal["below", "above"]
    threshold: float

    def __post_init__(self) -> None:
        if self.direction not in ("below", "above"):
            raise ValueError(f"direction must be 'below' or 'above', got {self.direction!r}")


@dataclass(frozen=True)
class LatentSchema:
    """Ordered latent factors plus the rule that defines each failure marginal."""

    factors: tuple[str, ...]
    failure_rules: Mapping[str, FailureRule]
    summary_factors: tuple[str, ...]
    binary_factors: tuple[str, ...] = ()  # stored as 0.0/1.0; MCMC moves flip rather than perturb

    def __post_init__(self) -> None:
        if len(set(self.factors)) != len(self.factors):
            raise ValueError("latent factor names must be unique")
        missing = [f for f in FAILURE_FIELDS if f not in self.failure_rules]
        extra = [f for f in self.failure_rules if f not in FAILURE_FIELDS]
        if missing or extra:
            raise ValueError(f"failure_rules must cover exactly FAILURE_FIELDS (missing={missing}, extra={extra})")
        for name, rule in self.failure_rules.items():
            if rule.factor not in self.factors:
                raise ValueError(f"rule {name} references unknown factor {rule.factor!r}")
        for factor in self.binary_factors:
            if factor not in self.factors:
                raise ValueError(f"binary factor {factor!r} is not a latent factor")
        for factor in self.summary_factors:
            if factor not in self.factors:
                raise ValueError(f"summary factor {factor!r} is not a latent factor")

    @property
    def dim(self) -> int:
        return len(self.factors)

    def index(self, factor: str) -> int:
        return self.factors.index(factor)

    def failure_indicators(self, particles: np.ndarray) -> np.ndarray:
        """(n, 8) boolean matrix for any (n, dim) particle array; columns follow FAILURE_FIELDS."""
        cols = []
        for name in FAILURE_FIELDS:
            rule = self.failure_rules[name]
            x = particles[:, self.index(rule.factor)]
            cols.append(x < rule.threshold if rule.direction == "below" else x > rule.threshold)
        return np.column_stack(cols)


# Factor names are the BinderHypothesis fields of the public predictive model;
# boolean factors (functional_epitope, assay_valid, model_valid) are stored as
# 0.0/1.0 columns. Stability, monomer_fraction and liability thresholds follow the
# Binder environment's own SELECT-correctness conditions (stability >= 0.60,
# monomer_fraction >= 0.60, liability <= 0.40). The affinity / kinetics thresholds
# (log_kd ~ log10 M, log_koff ~ log10 s^-1) have no canonical definition and remain
# PLACEHOLDERS chosen to separate the environment's good and defective worlds; replace
# them when the evaluator publishes its own.
BINDER_SCHEMA_PROVISIONAL = LatentSchema(
    factors=(
        "stability",
        "monomer_fraction",
        "log_kd",
        "log_koff",
        "functional_epitope",
        "developability_liability",
        "assay_valid",
        "model_valid",
    ),
    failure_rules={
        "p_folding_failure": FailureRule("stability", "below", 0.6),
        "p_aggregation_failure": FailureRule("monomer_fraction", "below", 0.6),
        "p_affinity_failure": FailureRule("log_kd", "above", -7.0),
        "p_kinetic_failure": FailureRule("log_koff", "above", -2.0),
        "p_epitope_failure": FailureRule("functional_epitope", "below", 0.5),
        "p_developability_failure": FailureRule("developability_liability", "above", 0.4),
        "p_assay_invalid": FailureRule("assay_valid", "below", 0.5),
        "p_model_invalid": FailureRule("model_valid", "below", 0.5),
    },
    summary_factors=(
        "stability",
        "monomer_fraction",
        "log_kd",
        "log_koff",
        "functional_epitope",
        "developability_liability",
    ),
    binary_factors=("functional_epitope", "assay_valid", "model_valid"),
)
