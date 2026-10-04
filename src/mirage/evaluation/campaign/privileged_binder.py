"""PRIVILEGED: evaluator-only access to the Binder BioPOMDP's private factorised truth.

This is the only module in the evaluation stack that reads environment-private state, and it
does so through exactly one attribute (``_hidden_by_candidate``). It must never be imported by
policies, belief code, the API, provenance or replay (enforced by tests/campaign/
test_campaign_trust_boundary.py). Core has not yet published an official evaluator-specific
accessor; when it does, only ``BinderPrivilegedOracle.__init__`` needs to change.

Label thresholds are versioned benchmark-engineering parameters (campaign-eval/1), not
biological facts. The same rules also define the benchmark belief schema, so the policies'
failure marginals and the evaluator's truth labels refer to the same definitions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mirage.belief.schema import BINDER_SCHEMA_PROVISIONAL, FailureRule, LatentSchema
from mirage.core import ScientificEnvironment
from mirage.environments.binder import SHOWCASE_SCENARIOS, BinderBioPOMDP, BinderHypothesis
from mirage.evaluation.campaign.harness import ARCHETYPE_TAGS, Archetype, World
from mirage.evaluation.campaign.truth import FailureLabels


@dataclass(frozen=True)
class LabelRules:
    """A factor 'fails' when it crosses its threshold. Boolean factors fail when False."""

    stability_min: float = 0.5
    monomer_min: float = 0.6
    log_kd_max: float = -7.0
    log_koff_max: float = -2.0
    liability_max: float = 0.4
    version: str = "campaign-eval/1/label-rules"

    def labels(self, h: BinderHypothesis) -> FailureLabels:
        return FailureLabels(
            folding_failure=h.stability < self.stability_min,
            aggregation_failure=h.monomer_fraction < self.monomer_min,
            affinity_failure=h.log_kd > self.log_kd_max,
            kinetic_failure=h.log_koff > self.log_koff_max,
            epitope_failure=not h.functional_epitope,
            developability_failure=h.developability_liability > self.liability_max,
            assay_invalid=not h.assay_valid,
            model_invalid=not h.model_valid,
        )

    def schema(self) -> LatentSchema:
        """The belief schema whose failure marginals use exactly these rules."""
        base = BINDER_SCHEMA_PROVISIONAL
        rules = dict(base.failure_rules)
        rules["p_folding_failure"] = FailureRule("stability", "below", self.stability_min)
        rules["p_aggregation_failure"] = FailureRule("monomer_fraction", "below", self.monomer_min)
        rules["p_affinity_failure"] = FailureRule("log_kd", "above", self.log_kd_max)
        rules["p_kinetic_failure"] = FailureRule("log_koff", "above", self.log_koff_max)
        rules["p_developability_failure"] = FailureRule("developability_liability", "above", self.liability_max)
        return LatentSchema(
            factors=base.factors,
            failure_rules=rules,
            summary_factors=base.summary_factors,
            binary_factors=base.binary_factors,
        )

    def as_dict(self) -> dict[str, float | str]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _digest(h: BinderHypothesis) -> str:
    import hashlib

    return hashlib.sha256(repr(h).encode()).hexdigest()


def world_digests(archetypes: Sequence[Archetype], seeds: Sequence[int]) -> dict[str, str]:
    """Digest of each seeded world, computed by resetting a fresh environment (no policy runs)."""
    out = {}
    for archetype in archetypes:
        for seed in seeds:
            env = BinderBioPOMDP.from_showcase(archetype.value)
            env.reset(seed=seed)
            out[f"{archetype.value}/{seed}"] = BinderPrivilegedOracle(env).world_digest()
    return out


class BinderPrivilegedOracle:
    """Failure labels for every candidate of one finished (or running) BinderBioPOMDP episode."""

    def __init__(self, env: ScientificEnvironment, rules: LabelRules | None = None) -> None:
        if not isinstance(env, BinderBioPOMDP):
            raise TypeError("BinderPrivilegedOracle requires a BinderBioPOMDP")
        hidden = getattr(env, "_hidden_by_candidate", None)
        if not isinstance(hidden, dict):
            raise RuntimeError("core no longer exposes _hidden_by_candidate; update the privileged accessor")
        self._hidden = hidden
        self._rules = rules or LabelRules()

    def failure_labels(self, candidate_id: str) -> FailureLabels:
        return self._rules.labels(self._hidden[candidate_id])

    def scenario_class(self) -> str:  # overridden by the harness' tagging
        return "BINDER"

    def world_digest(self) -> str:
        """Hash of the ROOT candidate's hidden state: identifies the exact seeded world.

        The public initial state is the same for every seed, so only this digest can show that
        two runs (or an appended policy) really played the identical world.
        """
        return _digest(self._hidden["binder-000"])


class BinderWorldSource:
    """WorldSource over the canonical showcase scenarios of core's BinderBioPOMDP."""

    def __init__(self, rules: LabelRules | None = None) -> None:
        self.rules = rules or LabelRules()
        self._names = {s.name: s for s in SHOWCASE_SCENARIOS}

    def worlds(self, archetype: Archetype, seeds: Sequence[int]) -> list[World]:
        scenario = self._names[archetype.value]
        scenario_class, regime = ARCHETYPE_TAGS[archetype]
        if scenario.world_mode.value != scenario_class.value:
            raise RuntimeError(
                f"core maps {archetype.value} to {scenario.world_mode.value}, expected {scenario_class.value}"
            )
        return [
            World(
                seed=seed,
                archetype=archetype.value,
                scenario_class=scenario_class.value,
                regime=regime.value,
                make_env=lambda name=archetype.value: BinderBioPOMDP.from_showcase(name),
                make_oracle=lambda env: BinderPrivilegedOracle(env, self.rules),
            )
            for seed in seeds
        ]
