"""Canonical public-data campaign controller for the Binder integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mirage.api.dto import StepDTO, event_dto, state_dto
from mirage.belief import BINDER_SCHEMA_PROVISIONAL, IndependentPrior, ParticleBelief, bernoulli, uniform
from mirage.belief.binder import BinderParticleModel
from mirage.belief.seeding import belief_stream_seed
from mirage.core import ActionType, AgentState, ScientificAction, StepResult
from mirage.environments.binder import BinderBioPOMDP, BinderWorldMode
from mirage.environments.binder.scenarios import BinderScenarioVersion
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
        self.belief = ParticleBelief.from_prior(
            BINDER_SCHEMA_PROVISIONAL,
            receptor_binder_prior(),
            n=particles,
            seed=belief_stream_seed(seed),
        )

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

    def _truth(self):
        return self._env.evaluator_truth(self._env.agent_state().active_candidate.candidate_id)

    def failure_labels(self, candidate_id: str) -> FailureLabels:
        return self._env.evaluator_truth(candidate_id).labels

    def scenario_class(self) -> str:
        return self._truth().scenario_class

    def regime(self) -> str:
        return self._truth().regime


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

def make_receptor_binder_service(store: PublicRecordStore, *, scenario: BinderWorldMode = BinderWorldMode.COMPOUND_FAILURE, code_version: str = "integration-h0", scenario_version: BinderScenarioVersion | None = None):
    """Wire the frozen EpisodeService to the Binder environment and belief adapter.

    ``scenario_version=None`` keeps the historical behaviour (Baseline V1, untagged environment
    id). Passing a version selects those semantics and records it in every public record.
    """
    import threading

    from mirage.api import EpisodeService
    from mirage.integration.catalogue import make_scenario_factory, verdict_from_evaluation

    version = scenario_version or BinderScenarioVersion.BASELINE_V1
    profile = ScientificProfile.RECEPTOR_BINDER_RESCUE.value
    pending = threading.local()

    def belief_factory(seed, _state):
        session = BinderBeliefSession(seed)
        box = getattr(pending, "box", None)
        if box is not None:  # GreedyEIG built just before this call, on this same request thread
            box["session"] = session
            pending.box = None
        return session

    def greedy_eig():
        box: dict = {}
        pending.box = box
        return GreedyEIGPolicy(BinderParticleModel(), lambda: box["session"].belief, seed=0, n_samples=32)

    return EpisodeService(
        env_factory=lambda: BinderBioPOMDP(scenario, scenario_version=version),
        store=store,
        belief_factory=belief_factory,
        policies={
            "random": lambda: RandomPolicy(allow_terminal=False),
            "fixed_pipeline": FixedPipelinePolicy,
            "rescue_planner": ReceptorRescuePlannerPolicy,
            "greedy_eig": greedy_eig,
        },
        environment_id=profile,
        default_environment_tag=None if scenario_version is None else version.value,
        code_version=code_version,
        scenario_factory=make_scenario_factory(scenario, version),
        verdict_fn=verdict_from_evaluation,
    )
