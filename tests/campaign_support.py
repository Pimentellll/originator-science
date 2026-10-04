"""Shared builders for provenance/evaluator/API tests (fixtures only, no results)."""

from mirage.evaluation.campaign.synthetic import (  # noqa: F401  (re-exported for tests)
    SyntheticOracle,
    TraceBuilder,
    confident,
    make_belief,
)

import hashlib

from mirage.core import (
    ActionType,
    AgentState,
    Candidate,
    ResourceState,
    ScientificAction,
    ScientificEnvironment,
    ScientificObservation,
    StepResult,
)
from mirage.evaluation.campaign.synthetic import SYNTHETIC_COSTS
from mirage.provenance.compat import ACTION_MEASUREMENTS, REDESIGN_ACTIONS, TERMINAL_ACTIONS

# A value no public payload may ever contain.
TRUTH_CANARY = 0.123456789


class StubLabEnv(ScientificEnvironment):
    """TEST DOUBLE ONLY: deterministic stand-in satisfying the ScientificEnvironment ABC.

    Not a simulator: observations are hash-derived so that same seed + same actions give the
    same public trace, and the private canary lets tests assert nothing leaks.
    """

    def __init__(self) -> None:
        self._state: AgentState | None = None
        self._seed = 0
        self._count = 0
        self._simulator_truth: dict[str, float] = {}

    def _u(self, *key) -> float:
        digest = hashlib.sha256(repr((self._seed, *key)).encode()).digest()
        return int.from_bytes(digest[:6], "big") / 2**48

    def reset(self, seed=None):
        self._seed = 0 if seed is None else int(seed)
        self._count = 0
        self._simulator_truth = {"log_kd": TRUTH_CANARY, "aggregated": float(self._u("agg") < 0.5)}
        root = Candidate(candidate_id="cand-0", generation=0)
        self._state = AgentState(
            active_candidate=root,
            candidates=(root,),
            resources=ResourceState(budget_remaining=60.0, sample_remaining=12.0, simulated_time=0.0, spr_instrument_health=1.0),
            observations=(),
        )
        return self._state

    def agent_state(self):
        assert self._state is not None
        return self._state

    def is_terminal(self):
        return self.agent_state().terminal

    def score(self):
        return 0.0

    def _affordable(self, kind):
        b, s, _ = SYNTHETIC_COSTS.get(kind, (0.0, 0.0, 0.0))
        r = self.agent_state().resources
        return r.budget_remaining >= b and r.sample_remaining >= s

    def available_actions(self):
        if self.is_terminal():
            return ()
        cand = self.agent_state().active_candidate.candidate_id
        return tuple(
            ScientificAction(action_type=k, candidate_id=cand)
            for k in ActionType
            if k in TERMINAL_ACTIONS or self._affordable(k)
        )

    def step(self, action):
        state = self.agent_state()
        if state.terminal:
            raise ValueError("episode is terminal")
        kind = action.action_type
        cand = action.candidate_id or state.active_candidate.candidate_id
        if cand not in {c.candidate_id for c in state.candidates}:
            raise ValueError("unknown candidate")
        r = state.resources
        observation = None
        active, candidates, terminal = state.active_candidate, state.candidates, kind in TERMINAL_ACTIONS
        if not terminal:
            if not self._affordable(kind):
                raise ValueError("insufficient resources")
            b, s, t = SYNTHETIC_COSTS[kind]
            health = r.spr_instrument_health
            self._count += 1
            if kind in ACTION_MEASUREMENTS:
                if kind == ActionType.MEASURE_SPR and self._simulator_truth["aggregated"]:
                    health = max(0.0, health - 0.3)
                observation = ScientificObservation(
                    action_type=kind,
                    candidate_id=cand,
                    measurements={n: round(self._u(kind.value, cand, n, self._count), 6) for n in ACTION_MEASUREMENTS[kind]},
                    quality="ok",
                )
            elif kind in REDESIGN_ACTIONS:
                parent = next(c for c in state.candidates if c.candidate_id == cand)
                active = Candidate(candidate_id=f"{cand}-r{self._count}", generation=parent.generation + 1, parent_candidate_id=cand)
                candidates = (*state.candidates, active)
            r = ResourceState(
                budget_remaining=r.budget_remaining - b,
                sample_remaining=r.sample_remaining - s,
                simulated_time=r.simulated_time + t,
                spr_instrument_health=health,
            )
        self._state = AgentState(
            active_candidate=active,
            candidates=candidates,
            resources=r,
            observations=(*state.observations, *([observation] if observation else [])),
            terminal=terminal,
        )
        return StepResult(action=action, observation=observation, state=self._state, terminal=terminal)
