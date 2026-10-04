"""Public, simulator-agnostic contracts for MIRAGE scientific environments.

These models deliberately describe only information an agent may observe. An
environment keeps its causal state privately and may expose it only through a
separate evaluator-specific mechanism.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _PublicModel(BaseModel):
    """Immutable public data with no undeclared fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ActionType(str, Enum):
    """Canonical actions shared by the binder MVP and future environments."""

    MEASURE_STABILITY = "MEASURE_STABILITY"
    MEASURE_SEC = "MEASURE_SEC"
    MEASURE_SPR = "MEASURE_SPR"
    MEASURE_EPITOPE = "MEASURE_EPITOPE"
    MEASURE_DEVELOPABILITY = "MEASURE_DEVELOPABILITY"
    VALIDATE_ASSAY = "VALIDATE_ASSAY"
    ORTHOGONAL_FUNCTION = "ORTHOGONAL_FUNCTION"

    REDESIGN_STABILITY = "REDESIGN_STABILITY"
    REDESIGN_SOLUBILITY = "REDESIGN_SOLUBILITY"
    REDESIGN_INTERFACE = "REDESIGN_INTERFACE"

    SELECT = "SELECT"
    REJECT = "REJECT"
    MODEL_INVALID = "MODEL_INVALID"
    ABSTAIN = "ABSTAIN"


class ScientificAction(_PublicModel):
    """A requested operation on a public candidate identifier."""

    action_type: ActionType
    candidate_id: str | None = Field(default=None, min_length=1, max_length=128)


class Candidate(_PublicModel):
    """Public candidate lineage metadata, intentionally excluding molecular truth."""

    candidate_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=0)
    parent_candidate_id: str | None = Field(default=None, min_length=1, max_length=128)


class ResourceState(_PublicModel):
    """Public laboratory resources and instrument condition."""

    budget_remaining: float = Field(ge=0)
    sample_remaining: float = Field(ge=0)
    simulated_time: float = Field(ge=0)
    spr_instrument_health: float = Field(ge=0, le=1)


class ScientificObservation(_PublicModel):
    """A single visible assay result, never a direct copy of latent state."""

    action_type: ActionType
    candidate_id: str = Field(min_length=1, max_length=128)
    value: float | None = None
    uncertainty: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=64)
    quality: str | None = Field(default=None, max_length=128)


class AgentState(_PublicModel):
    """Complete policy-visible state for one environment step."""

    active_candidate: Candidate
    candidates: tuple[Candidate, ...]
    resources: ResourceState
    observations: tuple[ScientificObservation, ...]
    terminal: bool = False


class StepResult(_PublicModel):
    """Visible result of applying a scientific action."""

    action: ScientificAction
    observation: ScientificObservation | None = None
    state: AgentState
    terminal: bool


class ScientificEnvironment(ABC):
    """Minimal interface implemented by scientific decision environments.

    Hidden simulator truth is purposefully absent from this public interface.
    """

    @abstractmethod
    def reset(self, seed: int | None = None) -> AgentState:
        """Start a reproducible episode and return only policy-visible state."""

    @abstractmethod
    def available_actions(self) -> tuple[ScientificAction, ...]:
        """Return currently valid public actions."""

    @abstractmethod
    def step(self, action: ScientificAction) -> StepResult:
        """Apply an action and return its visible result."""

    @abstractmethod
    def agent_state(self) -> AgentState:
        """Return the current policy-visible state."""

    @abstractmethod
    def is_terminal(self) -> bool:
        """Return whether the episode has ended."""

    @abstractmethod
    def score(self) -> float:
        """Return the environment score available after termination."""
