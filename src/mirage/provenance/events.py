"""Public provenance records (PROVENANCE_AND_REPLAY.md).

Everything here is public-only. Belief snapshots are stored as plain JSON mappings with
the semantic BeliefSummary fields so replay never needs the belief engine, PPO, an LLM or
the environment RNG, and so this package does not duplicate the belief workstream's type.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mirage.core import (
    ActionType,
    AgentState,
    ResourceState,
    ScientificAction,
    ScientificObservation,
)
from mirage.provenance.compat import REDESIGN_ACTIONS
from mirage.provenance.leakage import assert_public_payload

SCHEMA_VERSION = "mirage.provenance/1"

FAILURE_MARGINALS = (
    "p_folding_failure",
    "p_aggregation_failure",
    "p_affinity_failure",
    "p_kinetic_failure",
    "p_epitope_failure",
    "p_developability_failure",
    "p_assay_invalid",
    "p_model_invalid",
)
BELIEF_SCALARS = (*FAILURE_MARGINALS, "posterior_entropy", "effective_sample_size")
BELIEF_FIELDS = (*BELIEF_SCALARS, "continuous_means", "continuous_variances")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def validate_belief_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Check a public belief snapshot against the BELIEF_AND_POLICY_CONTRACT fields."""
    missing = [f for f in BELIEF_FIELDS if f not in payload]
    extra = [k for k in payload if k not in BELIEF_FIELDS]
    if missing or extra:
        raise ValueError(f"belief snapshot fields invalid: missing={missing} extra={extra}")
    for name in FAILURE_MARGINALS:
        value = payload[name]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be a probability in [0, 1]")
    for name in ("posterior_entropy", "effective_sample_size"):
        value = payload[name]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a nonnegative number")
    for name in ("continuous_means", "continuous_variances"):
        mapping = payload[name]
        if not isinstance(mapping, dict) or not all(
            isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool)
            for k, v in mapping.items()
        ):
            raise ValueError(f"{name} must map names to numbers")
    if any(v < 0 for v in payload["continuous_variances"].values()):
        raise ValueError("continuous_variances must be nonnegative")
    assert_public_payload(payload, where="belief snapshot")
    return payload


def belief_to_payload(summary: Any) -> dict[str, Any] | None:
    """Convert a BeliefSummary-like object (pydantic model or mapping) to a public snapshot."""
    if summary is None:
        return None
    raw = summary.model_dump(mode="json") if hasattr(summary, "model_dump") else dict(summary)
    return validate_belief_payload(json.loads(json.dumps(raw)))


class PolicyMetadata(_Frozen):
    """Public description of the acting policy. Config holds primitives only."""

    name: str = Field(min_length=1, max_length=128)
    version: str | None = Field(default=None, max_length=64)
    config: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def _public_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        assert_public_payload(value, where="policy config")
        return value


class ScientificEvent(_Frozen):
    """One applied action with its public effects."""

    episode_id: str = Field(min_length=1, max_length=128)
    step: int = Field(ge=0)
    candidate_id: str = Field(min_length=1, max_length=128)
    action: ScientificAction
    observation: ScientificObservation | None = None
    # Child of a REDESIGN_* action. Not in the D0 field list; needed to reconstruct
    # lineage from the public trace alone (reported to integration).
    child_candidate_id: str | None = Field(default=None, min_length=1, max_length=128)
    belief_before: dict[str, Any] | None = None
    belief_after: dict[str, Any] | None = None
    resources_before: ResourceState
    resources_after: ResourceState
    policy_name: str = Field(min_length=1, max_length=128)
    rationale: str | None = Field(default=None, max_length=1000)

    @field_validator("belief_before", "belief_after")
    @classmethod
    def _belief_ok(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else validate_belief_payload(value)

    @model_validator(mode="after")
    def _shape(self) -> ScientificEvent:
        is_redesign = self.action.action_type in REDESIGN_ACTIONS
        if is_redesign != (self.child_candidate_id is not None):
            raise ValueError("child_candidate_id is required for, and only for, REDESIGN_* actions")
        if self.observation is not None and (
            self.observation.action_type != self.action.action_type
            or self.observation.candidate_id != self.candidate_id
        ):
            raise ValueError("observation must belong to the event's action and candidate")
        return self


class EpisodeRecord(_Frozen):
    """A complete public episode: replayable without any model or RNG."""

    schema_version: str = SCHEMA_VERSION
    contract_version: str = Field(min_length=1, max_length=64)
    environment_id: str = Field(min_length=1, max_length=128)
    code_version: str = Field(min_length=1, max_length=64)
    episode_id: str = Field(min_length=1, max_length=128)
    seed: int
    initial_state: AgentState
    events: tuple[ScientificEvent, ...] = ()
    terminal_decision: ScientificAction | None = None
    policy: PolicyMetadata

    @model_validator(mode="after")
    def _episode_ids(self) -> EpisodeRecord:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {self.schema_version!r}")
        if any(e.episode_id != self.episode_id for e in self.events):
            raise ValueError("every event must carry the record's episode_id")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        )

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @property
    def is_terminal(self) -> bool:
        return self.terminal_decision is not None

    def action_sequence(self) -> tuple[ScientificAction, ...]:
        return tuple(e.action for e in self.events)


__all__ = [
    "ActionType",
    "BELIEF_FIELDS",
    "FAILURE_MARGINALS",
    "EpisodeRecord",
    "PolicyMetadata",
    "SCHEMA_VERSION",
    "ScientificEvent",
    "belief_to_payload",
    "validate_belief_payload",
]
