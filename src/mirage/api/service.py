"""Episode service: the controller between HTTP, the environment, belief, policies and
provenance. It holds the only reference to the environment object; nothing it returns
contains truth, and environment exceptions are never echoed to clients."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from mirage.api.dto import (
    ActionRequest,
    PublicStateDTO,
    RecommendationDTO,
    ReplayDTO,
    StepDTO,
    action_dto,
    event_dto,
    replay_dto,
    state_dto,
)
from mirage.core import AgentState, ScientificAction, ScientificEnvironment, StepResult
from mirage.provenance import EpisodeRecorder, PolicyMetadata, PublicRecordStore
from mirage.provenance.recorder import CONTRACT_VERSION


class BeliefSession(Protocol):
    """Per-episode belief tracker supplied by the belief workstream (adapter owned by integration)."""

    def summary(self) -> Any: ...

    def update(self, action: ScientificAction, result: StepResult) -> None: ...


BeliefFactory = Callable[[int, AgentState], BeliefSession]


class PolicyLike(Protocol):
    name: str

    def reset(self, seed: int | None = None) -> None: ...

    def choose_action(
        self, state: AgentState, belief: Any, available_actions: Sequence[ScientificAction]
    ) -> ScientificAction: ...


class ServiceError(Exception):
    """Client-safe error: ``public_message`` is the only text that may reach the response."""

    status = 400

    def __init__(self, public_message: str) -> None:
        super().__init__(public_message)
        self.public_message = public_message


class NotFound(ServiceError):
    status = 404


class Conflict(ServiceError):
    status = 409


class Forbidden(ServiceError):
    status = 403


class CorruptRecord(ServiceError):
    status = 500


class UnknownPolicy(ServiceError):
    status = 422


@dataclass
class _Live:
    episode_id: str
    seed: int
    env: ScientificEnvironment
    recorder: EpisodeRecorder
    belief: BeliefSession | None
    policy_name: str
    policy: PolicyLike | None
    lock: threading.Lock = field(default_factory=threading.Lock)


class EpisodeService:
    def __init__(
        self,
        env_factory: Callable[[], ScientificEnvironment],
        store: PublicRecordStore,
        *,
        belief_factory: BeliefFactory | None = None,
        policies: Mapping[str, Callable[[], PolicyLike]] | None = None,
        environment_id: str = "unspecified",
        code_version: str = "unversioned",
        id_factory: Callable[[], str] | None = None,
        max_live_episodes: int = 256,
    ) -> None:
        self._env_factory = env_factory
        self._store = store
        self._belief_factory = belief_factory
        self._policies = dict(policies or {})
        self._environment_id = environment_id
        self._code_version = code_version
        self._id_factory = id_factory or (lambda: f"ep-{uuid.uuid4().hex[:12]}")
        self._max_live = max_live_episodes
        self._live: dict[str, _Live] = {}
        self._guard = threading.Lock()

    @property
    def policy_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._policies))

    # ----------------------------------------------------------- helpers
    def _get(self, episode_id: str) -> _Live:
        live = self._live.get(episode_id)
        if live is None:
            raise NotFound("episode not found")
        return live

    def _state(self, live: _Live) -> PublicStateDTO:
        state = live.env.agent_state()
        belief = live.belief.summary() if live.belief else None
        available = () if state.terminal else tuple(live.env.available_actions())
        return state_dto(live.episode_id, state, belief, available)

    # ------------------------------------------------------------- API
    def create(self, seed: int | None, policy_name: str | None) -> PublicStateDTO:
        policy = None
        if policy_name is not None:
            if policy_name not in self._policies:
                raise UnknownPolicy("unknown policy")
            policy = self._policies[policy_name]()
        with self._guard:
            if len(self._live) >= self._max_live:
                raise Conflict("too many live episodes")
            episode_id = self._id_factory()
            if episode_id in self._live or self._store.exists(episode_id):
                raise Conflict("episode id collision")
            env = self._env_factory()
            used_seed = 0 if seed is None else seed
            initial = env.reset(seed=used_seed)
            if policy is not None:
                policy.reset(used_seed)
            recorder = EpisodeRecorder(
                episode_id=episode_id,
                seed=used_seed,
                initial_state=initial,
                policy=PolicyMetadata(name=policy_name or "interactive"),
                environment_id=self._environment_id,
                code_version=self._code_version,
                contract_version=CONTRACT_VERSION,
            )
            belief = self._belief_factory(used_seed, initial) if self._belief_factory else None
            live = _Live(episode_id, used_seed, env, recorder, belief, policy_name or "interactive", policy)
            self._live[episode_id] = live
        return self._state(live)

    def state(self, episode_id: str) -> PublicStateDTO:
        return self._state(self._get(episode_id))

    def available_actions(self, episode_id: str):
        return self._state(self._get(episode_id)).available_actions

    def act(self, episode_id: str, request: ActionRequest) -> StepDTO:
        live = self._get(episode_id)
        with live.lock:
            before = live.env.agent_state()
            if before.terminal:
                raise Conflict("episode already terminal")
            active = before.active_candidate.candidate_id
            matches = [
                a
                for a in live.env.available_actions()
                if a.action_type == request.action_type
                and (request.candidate_id or active) in (a.candidate_id, None)
            ]
            if not matches:
                raise Conflict("action not available")
            action = matches[0]
            belief_before = live.belief.summary() if live.belief else None
            try:
                result = live.env.step(action)
            except ValueError:
                raise Conflict("action rejected") from None
            if live.belief:
                live.belief.update(action, result)
            belief_after = live.belief.summary() if live.belief else None
            event = live.recorder.record_step(
                state_before=before,
                action=action,
                result=result,
                belief_before=belief_before,
                belief_after=belief_after,
                rationale=request.rationale,
            )
            if live.recorder.finished:
                self._store.save(live.recorder.finish())
            return StepDTO(event=event_dto(event), state=self._state(live))

    def recommend(self, episode_id: str) -> RecommendationDTO:
        live = self._get(episode_id)
        with live.lock:
            state = live.env.agent_state()
            if state.terminal:
                raise Conflict("episode already terminal")
            if live.policy is None:
                raise Conflict("no policy attached to this episode")
            if live.belief is None:
                raise Conflict("no belief engine configured")
            available = tuple(live.env.available_actions())
            choice = live.policy.choose_action(state, live.belief.summary(), available)
            if choice not in available:
                raise Conflict("policy proposed an unavailable action")
            return RecommendationDTO(episode_id=episode_id, policy_name=live.policy_name, action=action_dto(choice))

    def replay(self, episode_id: str) -> ReplayDTO:
        live = self._live.get(episode_id)
        if live is not None and not live.recorder.finished:
            with live.lock:
                return replay_dto(live.recorder.finish(), complete=False)
        try:
            return replay_dto(self._store.load(episode_id), complete=True)
        except FileNotFoundError:
            raise NotFound("episode not found") from None
        except ValueError as exc:
            if "unsafe identifier" in str(exc):
                raise NotFound("episode not found") from None
            # Schema or provenance failure: never echo validation detail (it may quote input).
            raise CorruptRecord("stored episode failed validation") from None
