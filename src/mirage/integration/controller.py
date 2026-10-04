"""Canonical public-data campaign controller for the Binder integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mirage.api.dto import StepDTO, event_dto, state_dto
from mirage.belief import BINDER_SCHEMA_PROVISIONAL, IndependentPrior, ParticleBelief, bernoulli, uniform
from mirage.belief.binder import BinderParticleModel
from mirage.core import ActionType, AgentState, ScientificAction, StepResult
from mirage.environments.binder import BinderBioPOMDP, BinderWorldMode
from mirage.evaluation.campaign import CampaignEvaluation, CampaignEvaluator, FailureLabels
from mirage.policies import FixedPipelinePolicy, GreedyEIGPolicy, RandomPolicy, ScientificPolicy
from mirage.policies.base import REDESIGN_ACTIONS
from mirage.provenance import EpisodeRecord, EpisodeRecorder, PolicyMetadata, PublicRecordStore
from mirage.integration.profiles import ScientificProfile, default_world_mode
from mirage.integration.rescue_policy import ReceptorRescuePlannerPolicy


def receptor_binder_prior() -> IndependentPrior:
    """Public semi-mechanistic prior, not an EGFR quantitative model."""
    return IndependentPrior(BINDER_SCHEMA_PROVISIONAL, {
        "stability": uniform(0.05, 1.0),
        "monomer_fraction": uniform(0.05, 1.0),
        "log_kd": uniform(-10.0, -5.0),
        "log_koff": uniform(-5.0, 0.0),
        "functional_epitope": bernoulli(0.75),
        "developability_liability": uniform(0.0, 1.0),
        "assay_valid": bernoulli(0.85),
        "model_valid": bernoulli(0.85),
    })


class BinderBeliefSession:
    """Adapter that gives EpisodeService/controller the existing update protocol."""

    def __init__(self, seed: int, *, particles: int = 256) -> None:
        self.model = BinderParticleModel()
        self.belief = ParticleBelief.from_prior(BINDER_SCHEMA_PROVISIONAL, receptor_binder_prior(), n=particles, seed=seed)

    def summary(self):
        return self.belief.summary()

    def update(self, action: ScientificAction, result: StepResult) -> None:
        if result.observation is not None:
            self.belief.observe(self.model, action, result.observation)
        elif action.action_type in REDESIGN_ACTIONS:
            self.belief.apply_redesign(self.model, action)


@dataclass(frozen=True)
class ControllerStep:
    """Only public DTOs leave the controller's policy-facing execution path."""

    dto: StepDTO
    terminal: bool


class _BinderOracle:
    """Evaluator-only adapter; never passed to a policy, DTO, or record."""

    def __init__(self, env: BinderBioPOMDP) -> None:
        self._env = env

    def failure_labels(self, candidate_id: str) -> FailureLabels:
        h = self._env._hidden_by_candidate[candidate_id]
        return FailureLabels(
            folding_failure=h.stability < 0.5,
            aggregation_failure=h.monomer_fraction < 0.8,
            affinity_failure=h.log_kd > -7.0,
            kinetic_failure=h.log_koff > -2.0,
            epitope_failure=not h.functional_epitope,
            developability_failure=h.developability_liability > 0.5,
            assay_invalid=not h.assay_valid,
            model_invalid=not h.model_valid,
        )

    def scenario_class(self) -> str:
        return self._env._world_mode.value

    def regime(self) -> str:
        return "path_dependent" if self._env._world_mode == BinderWorldMode.COMPOUND_FAILURE else "invalid" if self._env._world_mode in {BinderWorldMode.ASSAY_FAILURE, BinderWorldMode.MODEL_FAILURE} else "myopic"


class CampaignController:
    """One canonical reset/step loop with strict public policy inputs."""

    def __init__(self, store: PublicRecordStore, *, code_version: str = "integration-h0") -> None:
        self.store = store
        self.code_version = code_version
        self.env: BinderBioPOMDP | None = None
        self.session: BinderBeliefSession | None = None
        self.policy: ScientificPolicy | None = None
        self.recorder: EpisodeRecorder | None = None
        self.episode_id = ""

    def reset(self, seed: int, scenario: BinderWorldMode | None = None, profile: ScientificProfile = ScientificProfile.RECEPTOR_BINDER_RESCUE, policy_name: str = "fixed_pipeline") -> AgentState:
        mode = scenario or default_world_mode(profile)
        self.env = BinderBioPOMDP(mode)
        initial = self.env.reset(seed)
        self.session = BinderBeliefSession(seed)
        self.policy = self._policy(policy_name, seed)
        self.policy.reset(seed)
        self.episode_id = f"binder-{seed}-{policy_name}"
        self.recorder = EpisodeRecorder(
            episode_id=self.episode_id, seed=seed, initial_state=initial,
            policy=PolicyMetadata(name=self.policy.name),
            environment_id=profile.value, code_version=self.code_version,
        )
        return initial

    def step(self) -> ControllerStep:
        env, session, policy, recorder = self._ready()
        before = env.agent_state()
        available = env.available_actions()
        action = policy.choose_action(before, session.summary(), available)
        if action not in available:
            raise RuntimeError("policy proposed an unavailable action")
        belief_before = session.summary()
        result = env.step(action)
        session.update(action, result)
        event = recorder.record_step(state_before=before, action=action, result=result, belief_before=belief_before, belief_after=session.summary())
        record = recorder.finish()
        self.store.save(record)
        dto = StepDTO(event=event_dto(event), state=state_dto(self.episode_id, result.state, session.summary(), env.available_actions()))
        return ControllerStep(dto=dto, terminal=result.terminal)

    def record(self) -> EpisodeRecord:
        _, _, _, recorder = self._ready()
        return recorder.finish()

    def evaluate(self) -> CampaignEvaluation:
        env, _, _, recorder = self._ready()
        return CampaignEvaluator().evaluate(recorder.finish(), _BinderOracle(env))

    def _ready(self):
        if not all((self.env, self.session, self.policy, self.recorder)):
            raise RuntimeError("call reset() before step()")
        return self.env, self.session, self.policy, self.recorder

    def _policy(self, name: str, seed: int) -> ScientificPolicy:
        if name == "random":
            return RandomPolicy(seed=seed, allow_terminal=False)
        if name == "fixed_pipeline":
            return FixedPipelinePolicy()
        if name == "rescue_planner":
            return ReceptorRescuePlannerPolicy()
        if name == "greedy_eig":
            assert self.session is not None
            return GreedyEIGPolicy(self.session.model, lambda: self.session.belief, seed=seed, n_samples=32)
        raise ValueError(f"unknown policy {name!r}")

def make_receptor_binder_service(store: PublicRecordStore, *, scenario: BinderWorldMode = BinderWorldMode.COMPOUND_FAILURE, code_version: str = "integration-h0"):
    """Wire the frozen EpisodeService to the Binder environment and belief adapter."""
    from mirage.api import EpisodeService

    return EpisodeService(
        env_factory=lambda: BinderBioPOMDP(scenario),
        store=store,
        belief_factory=lambda seed, _state: BinderBeliefSession(seed),
        policies={"random": lambda: RandomPolicy(allow_terminal=False), "fixed_pipeline": FixedPipelinePolicy},
        environment_id=ScientificProfile.RECEPTOR_BINDER_RESCUE.value,
        code_version=code_version,
    )
