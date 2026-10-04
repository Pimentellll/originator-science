"""Public belief summary: the only belief view a policy receives."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BeliefSummary(BaseModel):
    """Marginal failure probabilities and moments of the particle posterior.

    The failure marginals are not mutually exclusive and need not sum to one.
    No particles, particle identities or latent values are exposed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    p_folding_failure: float = Field(ge=0.0, le=1.0)
    p_aggregation_failure: float = Field(ge=0.0, le=1.0)
    p_affinity_failure: float = Field(ge=0.0, le=1.0)
    p_kinetic_failure: float = Field(ge=0.0, le=1.0)
    p_epitope_failure: float = Field(ge=0.0, le=1.0)
    p_developability_failure: float = Field(ge=0.0, le=1.0)
    p_assay_invalid: float = Field(ge=0.0, le=1.0)
    p_model_invalid: float = Field(ge=0.0, le=1.0)

    # Shannon entropy (nats) of the joint failure-pattern distribution.
    posterior_entropy: float = Field(ge=0.0)
    continuous_means: dict[str, float]
    continuous_variances: dict[str, float]
    effective_sample_size: float = Field(gt=0.0)

    @field_validator("continuous_means", "continuous_variances")
    @classmethod
    def _finite(cls, value: dict[str, float]) -> dict[str, float]:
        if not all(math.isfinite(v) for v in value.values()):
            raise ValueError("continuous summaries must be finite")
        return value

    @field_validator("continuous_variances")
    @classmethod
    def _non_negative(cls, value: dict[str, float]) -> dict[str, float]:
        if any(v < 0 for v in value.values()):
            raise ValueError("variances must be non-negative")
        return value
