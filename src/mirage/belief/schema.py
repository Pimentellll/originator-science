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


# Factor names are the BinderHypothesis fields of the public predictive model;
# boolean factors (functional_epitope, assay_valid, model_valid) are stored as
# 0.0/1.0 columns. The failure THRESHOLDS are PLACEHOLDERS (log_kd ~ log10 M,
# log_koff ~ log10 s^-1, others in [0, 1]); no canonical scenario/evaluator
# definition of "failure regime" exists yet, so they must be replaced once it
# does, before any claim about calibration is made.
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
        "p_folding_failure": FailureRule("stability", "below", 0.5),
        "p_aggregation_failure": FailureRule("monomer_fraction", "below", 0.8),
        "p_affinity_failure": FailureRule("log_kd", "above", -7.0),
        "p_kinetic_failure": FailureRule("log_koff", "above", -2.0),
        "p_epitope_failure": FailureRule("functional_epitope", "below", 0.5),
        "p_developability_failure": FailureRule("developability_liability", "above", 0.5),
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
