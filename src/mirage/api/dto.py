"""Public DTOs: the only shapes that cross the HTTP trust boundary (FRONTEND_API_CONTRACT).

Every DTO is built field-by-field from public objects; nothing is ever produced by
dumping an environment, belief engine or evaluator object. All models forbid extras so a
new private field cannot slip through by accident.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mirage.core import ActionType, AgentState, Candidate, ResourceState, ScientificAction, ScientificObservation
from mirage.provenance import EpisodeRecord, Replay, ReplayFrame, ScientificEvent, validate_belief_payload


class _DTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- requests
class ResetRequest(_Request):
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    policy_name: str | None = Field(default=None, min_length=1, max_length=128)
    # Orchestration metadata chosen by the human running the demo; never policy input.
    scenario: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    scenario_version: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_]+$")


class ActionRequest(_Request):
    action_type: ActionType
    candidate_id: str | None = Field(default=None, min_length=1, max_length=128)
    rationale: str | None = Field(default=None, max_length=1000)


# --------------------------------------------------------------- responses
class CandidateDTO(_DTO):
    candidate_id: str
    generation: int
    parent_candidate_id: str | None


class ResourceDTO(_DTO):
    budget_remaining: float
    sample_remaining: float
    simulated_time: float
    spr_instrument_health: float


class ActionDTO(_DTO):
    action_type: ActionType
    candidate_id: str | None


class ObservationDTO(_DTO):
    action_type: ActionType
    candidate_id: str
    measurements: dict[str, float]
    quality: str
    notes: tuple[str, ...]


class BeliefDTO(_DTO):
    p_folding_failure: float
    p_aggregation_failure: float
    p_affinity_failure: float
    p_kinetic_failure: float
    p_epitope_failure: float
    p_developability_failure: float
    p_assay_invalid: float
    p_model_invalid: float
    posterior_entropy: float
    continuous_means: dict[str, float]
    continuous_variances: dict[str, float]
    effective_sample_size: float


class PublicStateDTO(_DTO):
    episode_id: str
    terminal: bool
    active_candidate: CandidateDTO
    candidates: tuple[CandidateDTO, ...]
    resources: ResourceDTO
    observations: tuple[ObservationDTO, ...]
    belief: BeliefDTO | None
    available_actions: tuple[ActionDTO, ...]


class EventDTO(_DTO):
    episode_id: str
    step: int
    candidate_id: str
    action: ActionDTO
    observation: ObservationDTO | None
    child_candidate_id: str | None
    belief_before: BeliefDTO | None
    belief_after: BeliefDTO | None
    resources_before: ResourceDTO
    resources_after: ResourceDTO
    policy_name: str
    rationale: str | None


class StepDTO(_DTO):
    event: EventDTO
    state: PublicStateDTO


class RecommendationDTO(_DTO):
    episode_id: str
    policy_name: str
    action: ActionDTO


class FrameDTO(_DTO):
    step: int
    action: ActionDTO
    observation: ObservationDTO | None
    belief: BeliefDTO | None
    resources: ResourceDTO
    candidates: tuple[CandidateDTO, ...]
    active_candidate_id: str
    terminal: bool
    policy_name: str
    rationale: str | None


class ReplayDTO(_DTO):
    episode_id: str
    complete: bool
    schema_version: str
    contract_version: str
    environment_id: str
    code_version: str
    seed: int
    policy_name: str
    initial_candidates: tuple[CandidateDTO, ...]
    initial_resources: ResourceDTO
    events: tuple[EventDTO, ...]
    frames: tuple[FrameDTO, ...]
    terminal_decision: ActionDTO | None


class HealthDTO(_DTO):
    status: str
    version: str


# ------------------------------------------------------------ conversions
def candidate_dto(c: Candidate) -> CandidateDTO:
    return CandidateDTO(candidate_id=c.candidate_id, generation=c.generation, parent_candidate_id=c.parent_candidate_id)


def resource_dto(r: ResourceState) -> ResourceDTO:
    return ResourceDTO(
        budget_remaining=r.budget_remaining,
        sample_remaining=r.sample_remaining,
        simulated_time=r.simulated_time,
        spr_instrument_health=r.spr_instrument_health,
    )


def action_dto(a: ScientificAction) -> ActionDTO:
    return ActionDTO(action_type=a.action_type, candidate_id=a.candidate_id)


def observation_dto(o: ScientificObservation | None) -> ObservationDTO | None:
    if o is None:
        return None
    return ObservationDTO(
        action_type=o.action_type,
        candidate_id=o.candidate_id,
        measurements={str(k): float(v) for k, v in o.measurements.items()},
        quality=o.quality,
        notes=tuple(o.notes),
    )


def belief_dto(snapshot: Any) -> BeliefDTO | None:
    """From a BeliefSummary-like object or a stored public snapshot mapping."""
    if snapshot is None:
        return None
    raw = snapshot.model_dump(mode="json") if hasattr(snapshot, "model_dump") else dict(snapshot)
    return BeliefDTO(**validate_belief_payload(raw))


def state_dto(
    episode_id: str,
    state: AgentState,
    belief: Any,
    available: tuple[ScientificAction, ...],
) -> PublicStateDTO:
    return PublicStateDTO(
        episode_id=episode_id,
        terminal=state.terminal,
        active_candidate=candidate_dto(state.active_candidate),
        candidates=tuple(candidate_dto(c) for c in state.candidates),
        resources=resource_dto(state.resources),
        observations=tuple(observation_dto(o) for o in state.observations),  # type: ignore[misc]
        belief=belief_dto(belief),
        available_actions=tuple(action_dto(a) for a in available),
    )


def event_dto(e: ScientificEvent) -> EventDTO:
    return EventDTO(
        episode_id=e.episode_id,
        step=e.step,
        candidate_id=e.candidate_id,
        action=action_dto(e.action),
        observation=observation_dto(e.observation),
        child_candidate_id=e.child_candidate_id,
        belief_before=belief_dto(e.belief_before),
        belief_after=belief_dto(e.belief_after),
        resources_before=resource_dto(e.resources_before),
        resources_after=resource_dto(e.resources_after),
        policy_name=e.policy_name,
        rationale=e.rationale,
    )


def frame_dto(f: ReplayFrame) -> FrameDTO:
    return FrameDTO(
        step=f.step,
        action=action_dto(f.action),
        observation=observation_dto(f.observation),
        belief=belief_dto(f.belief),
        resources=resource_dto(f.resources),
        candidates=tuple(candidate_dto(c) for c in f.candidates),
        active_candidate_id=f.active_candidate_id,
        terminal=f.terminal,
        policy_name=f.policy_name,
        rationale=f.rationale,
    )


def replay_dto(record: EpisodeRecord, *, complete: bool) -> ReplayDTO:
    replay = Replay(record)
    return ReplayDTO(
        episode_id=record.episode_id,
        complete=complete,
        schema_version=record.schema_version,
        contract_version=record.contract_version,
        environment_id=record.environment_id,
        code_version=record.code_version,
        seed=record.seed,
        policy_name=record.policy.name,
        initial_candidates=tuple(candidate_dto(c) for c in record.initial_state.candidates),
        initial_resources=resource_dto(record.initial_state.resources),
        events=tuple(event_dto(e) for e in record.events),
        frames=tuple(frame_dto(f) for f in replay),
        terminal_decision=action_dto(record.terminal_decision) if record.terminal_decision else None,
    )
