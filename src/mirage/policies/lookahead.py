"""Model-based belief-rollout planner: the strong long-horizon baseline.

Closed-loop sparse-sampling expectimax over the SAME public predictive model GreedyEIG
uses. At every node the planner may stop (take the best terminal decision), run one
more assay, or redesign; it looks ``depth`` actions ahead and executes the first
action of the best plan (receding horizon).

    V(node, d) = max( stop(node),  max_a  Q(node, a, d) )
    Q(node, a, d) = - resource_penalty(a) + E_y[ V(node after a, y, d-1) ]
    stop(node) = max_terminal E[utility | belief] - entropy_weight * H(belief)

Expectation over outcomes y uses seeded Monte Carlo from HYPOTHETICAL particles of the
node's belief (``model.sample_observation``); each sampled y reweights the particles
through ``model.log_likelihood`` and the resulting posterior is likelihood-tempered
(shared with EIG) so a finite particle set cannot fake certainty. A redesign pushes the
node's particles through the model's public redesign transition (one shared child cloud
per redesign type, so alternatives are compared on common random numbers).

Reasoned about explicitly: expected future posterior entropy (shaping term), experiment
cost, sample use, time, terminal utility, redesign, and SPR instrument path dependence:
an SPR reading that comes back "degraded" (public quality flag) damages instrument
health in the rollout, and SPR is not planned below a usable-health floor because the
instrument then returns degraded readings regardless of the molecule.

Limits (deliberate, documented): at most one redesign per plan; no repeat-sampling
correlation (a repeated assay draws fresh noise); the planning posterior is tempered;
the belief handle is the same as GreedyEIG's (``belief_source``). The terminal utilities
are the planner's own configurable approximation of the evaluator, never the evaluator.

Cost. With depth 2, measurement sample counts (S1, S2) and a beam B of second-step
measurements over P planning particles, one decision runs about
    A * S1  +  A * S1 * (B * S2)      likelihood sweeps of P particles each
(A <= 7 first-step assays), plus 3 cheap redesign clouds. Depth d multiplies by
roughly (B * S)^(d-1).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

import numpy as np

from mirage.belief.acquisition import tempered_posteriors
from mirage.belief.decision import TERMINAL_ORDER, TerminalUtility, correct_terminal_masks, gated_terminal_utilities
from mirage.belief.particles import ParticleBelief, binary_entropy
from mirage.belief.predictive import ParticlePredictiveModel
from mirage.belief.schema import FAILURE_FIELDS
from mirage.belief.resampling import systematic_resample
from mirage.belief.summary import BeliefSummary
from mirage.core.contracts import ActionType, AgentState, ScientificAction
from mirage.policies.base import (
    MEASUREMENT_ACTIONS,
    REDESIGN_ACTIONS,
    PolicyError,
    ScientificPolicy,
    check_belief_in_sync,
    usable_actions,
)


ASSAY_COLUMN = FAILURE_FIELDS.index("p_assay_invalid")


# What each redesign is documented to repair (scientific-spec/REDESIGN_MODEL.md).
REDESIGN_TARGETS: Mapping[ActionType, tuple[str, ...]] = {
    ActionType.REDESIGN_STABILITY: ("p_folding_failure",),
    ActionType.REDESIGN_SOLUBILITY: ("p_aggregation_failure", "p_developability_failure"),
    ActionType.REDESIGN_INTERFACE: ("p_affinity_failure", "p_kinetic_failure"),
}


@dataclass(frozen=True)
class ActionCost:
    budget: float
    sample: float
    time: float


# The Binder resource model's configured costs (docs/scientific-spec/RESOURCE_MODEL.md says
# costs are configurable simulator parameters, so policies take them as public config).
# tests/policies/test_policy_lookahead.py pins this table to the environment's own.
DEFAULT_ACTION_COSTS: Mapping[ActionType, ActionCost] = {
    ActionType.MEASURE_STABILITY: ActionCost(1.0, 0.5, 0.5),
    ActionType.MEASURE_SEC: ActionCost(1.0, 0.5, 0.5),
    ActionType.MEASURE_SPR: ActionCost(2.0, 1.0, 1.0),
    ActionType.MEASURE_EPITOPE: ActionCost(1.0, 0.4, 0.5),
    ActionType.MEASURE_DEVELOPABILITY: ActionCost(1.0, 0.4, 0.5),
    ActionType.VALIDATE_ASSAY: ActionCost(0.75, 0.1, 0.25),
    ActionType.ORTHOGONAL_FUNCTION: ActionCost(1.5, 0.25, 0.75),
    ActionType.REDESIGN_STABILITY: ActionCost(2.0, 1.0, 1.0),
    ActionType.REDESIGN_SOLUBILITY: ActionCost(2.0, 1.0, 1.0),
    ActionType.REDESIGN_INTERFACE: ActionCost(2.0, 1.0, 1.0),
}


@dataclass(frozen=True)
class SPRHealthModel:
    """Public path-dependence of the SPR instrument (pinned to the environment by a test)."""

    damage: float = 0.28  # health lost per degraded SPR reading
    min_usable_health: float = 0.70  # below this SPR returns degraded readings regardless


@dataclass(frozen=True)
class LookaheadConfig:
    depth: int = 2
    samples: tuple[int, ...] = (6, 6, 4)  # outcome samples per assay at each depth level
    measurement_beam: tuple[int, ...] = (7, 4, 3)  # assays considered at each depth level
    planning_particles: int | None = 256  # thin the belief for planning (None = use all)
    min_posterior_ess: float = 10.0
    # A correctly rejected failure is worth less than a rescued, verified binder (planner default).
    utility: TerminalUtility = TerminalUtility(correct_reject=0.6)
    entropy_weight: float = 0.01  # utility per nat of mechanism entropy removed by a measurement
    assay_resolved: float = 0.10  # SELECT/MODEL_INVALID need p(assay invalid) <= this after a control
    # A redesign is only planned once its target mechanism is probable (None disables the gate).
    redesign_evidence: float | None = 0.5
    budget_penalty: float = 0.02  # matches the environment's local score
    sample_penalty: float = 0.02
    time_penalty: float = 0.01
    stop_margin: float = 1e-9
    spr: SPRHealthModel = SPRHealthModel()


@dataclass
class _Cloud:
    particles: np.ndarray
    indicators: np.ndarray  # (P, 8) bool
    masks: np.ndarray  # (P, 4) float terminal-correctness
    ind_float: np.ndarray


@dataclass
class _Node:
    cloud: _Cloud
    log_w: np.ndarray
    budget: float
    sample: float
    health: float
    diagnostic: bool
    assay_tested: bool = False
    redesigned: bool = False


@dataclass(frozen=True)
class PlanDiagnostics:
    q_values: dict[ActionType, float]
    stop_value: float
    terminal_utilities: dict[ActionType, float]
    likelihood_sweeps: int
    seconds: float
    chosen: ActionType


def _make_cloud(schema, particles: np.ndarray) -> _Cloud:
    ind = schema.failure_indicators(particles)
    return _Cloud(particles, ind, correct_terminal_masks(ind), ind.astype(float))


class LookaheadPolicy(ScientificPolicy):
    """Seeded, deterministic depth-``config.depth`` belief-rollout planner."""

    name = "lookahead"

    def __init__(
        self,
        model: ParticlePredictiveModel,
        belief_source: Callable[[], ParticleBelief],
        *,
        seed: int = 0,
        config: LookaheadConfig | None = None,
        costs: Mapping[ActionType, ActionCost] | None = None,
    ) -> None:
        self.config = config or LookaheadConfig()
        if not 1 <= self.config.depth <= len(self.config.samples):
            raise ValueError("depth must be between 1 and len(config.samples)")
        self.model, self.belief_source = model, belief_source
        self.costs = dict(costs or DEFAULT_ACTION_COSTS)
        self._base_seed = seed
        self._rng = np.random.default_rng(seed)
        self.last_plan: PlanDiagnostics | None = None
        self._sweeps = 0
        self._beam: tuple[ActionType, ...] = ()
        self._child_clouds: dict[ActionType, _Cloud] = {}
        self._cid = ""
        self._decision_key = 0

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self._base_seed = seed
        self._rng = np.random.default_rng(self._base_seed)
        self.last_plan = None

    # ------------------------------------------------------------------ values

    def _terminal_eu(self, weights: np.ndarray, cloud: _Cloud, node: _Node) -> np.ndarray:
        """Gated expected utility of each terminal (see ``gated_terminal_utilities``)."""
        return gated_terminal_utilities(
            weights, cloud.masks, cloud.ind_float[:, ASSAY_COLUMN], self.config.utility,
            diagnostic=node.diagnostic, assay_tested=node.assay_tested, assay_resolved=self.config.assay_resolved,
        )

    def _leaf(self, weights: np.ndarray, cloud: _Cloud, node: _Node) -> np.ndarray:
        """Best terminal expected utility; weights (m, P) or (P,)."""
        return self._terminal_eu(weights, cloud, node).max(axis=-1)

    def _redesign_justified(self, weights: np.ndarray, node: _Node, t: ActionType) -> bool:
        gate = self.config.redesign_evidence
        if gate is None:
            return True
        p = weights @ node.cloud.ind_float
        return any(p[FAILURE_FIELDS.index(f)] >= gate for f in REDESIGN_TARGETS[t])

    def _penalty(self, action_type: ActionType) -> float:
        c, cfg = self.costs[action_type], self.config
        return cfg.budget_penalty * c.budget + cfg.sample_penalty * c.sample + cfg.time_penalty * c.time

    def _affordable(self, node: _Node, action_type: ActionType) -> bool:
        c = self.costs.get(action_type)
        return c is not None and node.budget >= c.budget and node.sample >= c.sample

    def _measurements(self, node: _Node, level: int, pool: Sequence[ActionType]) -> list[ActionType]:
        out = [t for t in pool if self._affordable(node, t)]
        if node.health < self.config.spr.min_usable_health:
            out = [t for t in out if t != ActionType.MEASURE_SPR]
        return out[: self.config.measurement_beam[level]]

    def _value(self, node: _Node, depth_left: int) -> float:
        level = self.config.depth - depth_left
        weights = np.exp(node.log_w - np.max(node.log_w))
        weights /= weights.sum()
        best = float(self._leaf(weights, node.cloud, node))
        if depth_left == 0:
            return best
        sources = self._sources(weights, level)
        for t in self._measurements(node, level, self._beam):
            best = max(best, self._q_measure(node, ScientificAction(action_type=t, candidate_id=self._cid), depth_left, level, sources))
        if not node.redesigned:
            for t in sorted(self._child_clouds, key=lambda x: x.value):
                if self._affordable(node, t) and self._redesign_justified(weights, node, t):
                    best = max(best, self._q_redesign(node, t, depth_left))
        return best

    def _q_redesign(self, node: _Node, t: ActionType, depth_left: int) -> float:
        c = self.costs[t]
        child = _Node(self._child_clouds[t], node.log_w, node.budget - c.budget, node.sample - c.sample, node.health, node.diagnostic, node.assay_tested, True)
        return -self._penalty(t) + self._value(child, depth_left - 1)

    def _sources(self, weights: np.ndarray, level: int) -> np.ndarray:
        """Hypothetical source particles for a node, shared by every action evaluated there
        (common random numbers, so action values are compared on the same hypothetical worlds)."""
        return systematic_resample(weights, self._rng, size=self.config.samples[level])

    def _noise(self, source: int, action_type: ActionType, level: int) -> np.random.Generator:
        """Observation noise keyed by (decision, source, assay, level): the same hypothetical
        world measured by the same assay at the same level sees the same noise."""
        return np.random.default_rng([self._decision_key, int(source), list(ActionType).index(action_type), level])

    def _q_measure(
        self, node: _Node, action: ScientificAction, depth_left: int, level: int, sources: np.ndarray
    ) -> float:
        cfg, cloud, t = self.config, node.cloud, action.action_type
        n_s = len(sources)
        w = np.exp(node.log_w - np.max(node.log_w))
        w /= w.sum()
        ll = np.empty((n_s, len(node.log_w)))
        degraded = np.zeros(n_s, dtype=bool)
        for m, j in enumerate(sources):
            y = self.model.sample_observation(cloud.particles[j], action, self._noise(j, t, level))
            ll[m] = self.model.log_likelihood(y, cloud.particles, action)
            degraded[m] = y.quality == "degraded"
        self._sweeps += n_s
        ok = np.isfinite(ll.max(axis=1))
        if not ok.any():
            return -np.inf
        ll, degraded = ll[ok], degraded[ok]
        post, _ = tempered_posteriors(node.log_w, ll, cfg.min_posterior_ess)
        c = self.costs[t]
        tested = node.assay_tested or t == ActionType.VALIDATE_ASSAY
        measured = _Node(cloud, node.log_w, node.budget - c.budget, node.sample - c.sample, node.health, True, tested, node.redesigned)
        # entropy shaping: reward only the mechanism entropy a MEASUREMENT removes
        h_before = float(binary_entropy(w @ cloud.ind_float).sum())
        h_after = binary_entropy(post @ cloud.ind_float).sum(axis=-1)
        shaping = cfg.entropy_weight * (h_before - float(h_after.mean()))
        if depth_left == 1:
            value = float(self._leaf(post, cloud, measured).mean())
        else:
            total = 0.0
            for m in range(len(post)):
                health = node.health - (cfg.spr.damage if (t == ActionType.MEASURE_SPR and degraded[m]) else 0.0)
                with np.errstate(divide="ignore"):
                    child = _Node(cloud, np.log(post[m]), measured.budget, measured.sample, max(0.0, health), True, tested, node.redesigned)
                total += self._value(child, depth_left - 1)
            value = total / len(post)
        return value + shaping - self._penalty(t)

    # ---------------------------------------------------------------- decision

    def choose_action(
        self,
        state: AgentState,
        belief: BeliefSummary,
        available_actions: Sequence[ScientificAction],
    ) -> ScientificAction:
        self._require_decidable(state, available_actions)
        started = time.perf_counter()
        particle_belief = self.belief_source()
        check_belief_in_sync(particle_belief, belief)
        cfg = self.config

        usable = usable_actions(state, available_actions)
        self._cid = state.active_candidate.candidate_id
        schema = particle_belief.schema
        particles, weights = particle_belief.particles, particle_belief.weights
        if cfg.planning_particles is not None and cfg.planning_particles < particle_belief.n:
            idx = systematic_resample(weights, self._rng, size=cfg.planning_particles)
            particles, log_w = particles[idx], np.full(cfg.planning_particles, -np.log(cfg.planning_particles))
        else:
            log_w = particle_belief.log_weights
        cloud = _make_cloud(schema, particles)
        res = state.resources
        diagnostic = bool(state.observations)
        tested = any(o.action_type == ActionType.VALIDATE_ASSAY for o in state.observations)
        root = _Node(cloud, log_w, res.budget_remaining, res.sample_remaining, res.spr_instrument_health, diagnostic, tested)

        # redesign child clouds: one shared draw per redesign type (common random numbers)
        self._child_clouds = {
            t: _make_cloud(schema, self.model.redesign(cloud.particles, ScientificAction(action_type=t, candidate_id=self._cid), self._rng))
            for t in sorted(REDESIGN_ACTIONS, key=lambda x: x.value)
            if t in usable
        }
        measurement_pool = [t for t in sorted(MEASUREMENT_ACTIONS, key=lambda x: x.value) if t in usable]
        self._sweeps = 0
        self._decision_key = int(self._rng.integers(2**31))

        # beam for deeper levels: rank assays by their one-step value at the root
        root_sources = self._sources(np.exp(root.log_w), 0)
        one_step = {
            t: self._q_measure(root, usable[t], 1, 0, root_sources) for t in self._measurements(root, 0, measurement_pool)
        }
        self._beam = tuple(sorted(one_step, key=lambda t: (-one_step[t], t.value)))

        q: dict[ActionType, float] = {}
        for t in self._beam:
            q[t] = one_step[t] if cfg.depth == 1 else self._q_measure(root, usable[t], cfg.depth, 0, root_sources)
        w = np.exp(root.log_w - np.max(root.log_w))
        w /= w.sum()
        for t in sorted(self._child_clouds, key=lambda x: x.value):
            if self._affordable(root, t) and self._redesign_justified(w, root, t):
                q[t] = self._q_redesign(root, t, cfg.depth)
        stop = float(self._leaf(w, cloud, root))
        eu = self._terminal_eu(particle_belief.weights, _make_cloud(schema, particle_belief.particles), root)
        terminal_choices = [(float(eu[k]), -k, TERMINAL_ORDER[k]) for k in range(4) if TERMINAL_ORDER[k] in usable and np.isfinite(eu[k])]
        best_t = max(q, key=lambda t: (q[t], -list(ActionType).index(t))) if q else None

        if best_t is not None and q[best_t] > stop + cfg.stop_margin:
            chosen = usable[best_t]
        elif terminal_choices:
            chosen = usable[max(terminal_choices)[2]]
        elif any(t in usable for t in TERMINAL_ORDER):  # only gated ABSTAIN-like options remain
            chosen = usable[next(t for t in TERMINAL_ORDER if t in usable)]
        else:
            raise PolicyError("no terminal action is available and nothing is affordable")
        self.last_plan = PlanDiagnostics(
            q_values=q,
            stop_value=stop,
            terminal_utilities={TERMINAL_ORDER[k]: float(eu[k]) for k in range(4)},
            likelihood_sweeps=self._sweeps,
            seconds=time.perf_counter() - started,
            chosen=chosen.action_type,
        )
        return chosen
