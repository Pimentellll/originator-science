"""Baseline-V1 belief configuration, reproduced from its recorded manifest (campaign-eval/1).

Agent-side prior: independent factors, conditioned on 'the campaign started from a downstream
failure' (at least one failure rule fires). Label rules: stability 0.5, monomer 0.6, log_kd -7,
log_koff -2, liability 0.4. Used by the posterior-convergence audit and its regression tests;
nothing here reads an environment or any hidden state.
"""

from __future__ import annotations

import json
from pathlib import Path

from mirage.belief import (
    BINDER_SCHEMA_PROVISIONAL as _BASE,
    ConditionedPrior,
    DegenerateBeliefError,
    FailureRule,
    IndependentPrior,
    LatentSchema,
    ParticleBelief,
    bernoulli,
    uniform,
)
from mirage.belief.binder import BinderParticleModel
from mirage.core.contracts import ScientificAction, ScientificObservation

FIXTURES = Path(__file__).parent / "fixtures" / "belief_traces"

_rules = dict(_BASE.failure_rules)
_rules["p_folding_failure"] = FailureRule("stability", "below", 0.5)
_rules["p_aggregation_failure"] = FailureRule("monomer_fraction", "below", 0.6)
_rules["p_affinity_failure"] = FailureRule("log_kd", "above", -7.0)
_rules["p_kinetic_failure"] = FailureRule("log_koff", "above", -2.0)
_rules["p_developability_failure"] = FailureRule("developability_liability", "above", 0.4)
SCHEMA_V1 = LatentSchema(_BASE.factors, _rules, _BASE.summary_factors, _BASE.binary_factors)
MODEL_V1 = BinderParticleModel(schema=SCHEMA_V1)
_BASE_PRIOR = IndependentPrior(
    SCHEMA_V1,
    {
        "stability": uniform(0.0, 1.0),
        "monomer_fraction": uniform(0.05, 1.0),
        "log_kd": uniform(-10.0, -5.0),
        "log_koff": uniform(-5.0, 1.0),
        "functional_epitope": bernoulli(0.5),
        "developability_liability": uniform(0.0, 1.0),
        "assay_valid": bernoulli(0.75),
        "model_valid": bernoulli(0.75),
    },
)
PRIOR_V1 = ConditionedPrior(_BASE_PRIOR, lambda z: ParticleBelief(SCHEMA_V1, z).failure_indicators().any(axis=1))


def load_traces(*files: str) -> dict[str, list[tuple[ScientificAction, ScientificObservation]]]:
    """Public (action, observation) sequences keyed by trace name."""
    out = {}
    for name in files or ("public_traces.json", "v1_public_traces.json"):
        for key, trace in json.loads((FIXTURES / name).read_text()).items():
            out[key] = [(ScientificAction(**s["action"]), ScientificObservation(**s["observation"])) for s in trace["steps"]]
    return out


def fresh_belief(n: int, seed: int, **kw) -> ParticleBelief:
    return ParticleBelief.from_prior(SCHEMA_V1, PRIOR_V1, n=n, seed=seed, ess_threshold=0.5, **kw)


def replay(trace, n: int, seed: int, **kw):
    """Replay a public trace; returns the belief and the per-observation UpdateInfo list
    (None where the public likelihood could not explain the observation)."""
    belief, infos = fresh_belief(n, seed, **kw), []
    for action, observation in trace:
        try:
            infos.append(belief.observe(MODEL_V1, action, observation))
        except DegenerateBeliefError:
            infos.append(None)
    return belief, infos
