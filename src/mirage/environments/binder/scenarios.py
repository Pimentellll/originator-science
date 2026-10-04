"""Seeded procedural Binder worlds and versioned private scenario semantics."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import numpy as np
from mirage.environments.binder.predictive import BinderHypothesis

class BinderWorldMode(str, Enum):
    SINGLE_FAILURE = "SINGLE_FAILURE"
    COMPOUND_FAILURE = "COMPOUND_FAILURE"
    ASSAY_FAILURE = "ASSAY_FAILURE"
    MODEL_FAILURE = "MODEL_FAILURE"
    MIXED = "MIXED"

class BinderScenarioVersion(str, Enum):
    """V1 is frozen; V2 makes canonical scenario mechanisms contractual."""
    BASELINE_V1 = "BASELINE_V1"
    SEMANTICS_V2 = "SEMANTICS_V2"

@dataclass(frozen=True)
class ScenarioSignature:
    """Evaluator-only contract for one named V2 world."""
    primary_failure_mechanisms: tuple[str, ...]
    forbidden_primary_mechanisms: tuple[str, ...]
    secondary_consequences: tuple[str, ...]
    expected_assay_signature: tuple[str, ...]

@dataclass(frozen=True)
class ShowcaseScenario:
    name: str
    world_mode: BinderWorldMode
    description: str
    signature: ScenarioSignature

SHOWCASE_SCENARIOS: tuple[ShowcaseScenario, ...] = (
    ShowcaseScenario("instability", BinderWorldMode.SINGLE_FAILURE, "A folding failure with otherwise usable binding.", ScenarioSignature(("folding_failure",), ("aggregation_failure", "affinity_failure", "kinetic_failure", "epitope_failure", "developability_failure"), ("reduced stability assay signal",), ("stability_proxy low", "SEC monomer_fraction non-failing", "SPR nominal"))),
    ShowcaseScenario("aggregation_kinetic_defect", BinderWorldMode.COMPOUND_FAILURE, "Aggregation plus a fast-dissociation kinetic defect.", ScenarioSignature(("aggregation_failure", "kinetic_failure"), ("folding_failure", "affinity_failure", "epitope_failure", "developability_failure"), ("degraded SPR information", "SPR instrument health loss after premature SPR"), ("SEC monomer_fraction low", "SPR degraded", "log_koff indicates fast dissociation"))),
    ShowcaseScenario("broken_assay", BinderWorldMode.ASSAY_FAILURE, "A good molecule with an invalid downstream assay.", ScenarioSignature(("assay_invalid",), ("folding_failure", "aggregation_failure", "affinity_failure", "kinetic_failure", "epitope_failure", "developability_failure", "model_invalid"), ("functional readout is uninterpretable",), ("molecular assays nominal", "assay control low"))),
    ShowcaseScenario("invalid_biological_model", BinderWorldMode.MODEL_FAILURE, "A good molecule and assay in an invalid biological model.", ScenarioSignature(("model_invalid",), ("folding_failure", "aggregation_failure", "affinity_failure", "kinetic_failure", "epitope_failure", "developability_failure", "assay_invalid"), ("molecular engagement does not establish expected function",), ("molecular assays nominal", "assay control valid", "orthogonal interpretation misleading"))),
    ShowcaseScenario("misleading_proxy_trap", BinderWorldMode.MIXED, "Attractive proxy readouts conceal functional and developability failure.", ScenarioSignature(("epitope_failure", "developability_failure"), ("folding_failure", "aggregation_failure", "affinity_failure", "kinetic_failure", "assay_invalid", "model_invalid"), ("favourable affinity proxy is non-diagnostic",), ("SPR nominal with favourable affinity proxy", "epitope signal low", "developability proxy high"))),
)
_SCENARIOS_BY_NAME = {scenario.name: scenario for scenario in SHOWCASE_SCENARIOS}

def showcase_scenario(name: str) -> ShowcaseScenario:
    try:
        return _SCENARIOS_BY_NAME[name]
    except KeyError as error:
        choices = ", ".join(_SCENARIOS_BY_NAME)
        raise ValueError(f"unknown Binder showcase scenario {name!r}; choose one of {choices}") from error

def showcase_for_mode(mode: BinderWorldMode) -> ShowcaseScenario:
    return next(s for s in SHOWCASE_SCENARIOS if s.world_mode == BinderWorldMode(mode))

def sample_world(mode: BinderWorldMode, rng: np.random.Generator, version: BinderScenarioVersion = BinderScenarioVersion.BASELINE_V1) -> BinderHypothesis:
    """Create a factorised private world; V1 remains byte-for-byte behaviourally frozen."""
    mode, version = BinderWorldMode(mode), BinderScenarioVersion(version)
    if version == BinderScenarioVersion.SEMANTICS_V2:
        return _sample_v2(mode, rng)
    normal = rng.normal
    if mode == BinderWorldMode.SINGLE_FAILURE:
        return BinderHypothesis(float(np.clip(normal(0.22, 0.035), 0.10, 0.32)), float(np.clip(normal(0.83, 0.04), 0.65, 0.95)), float(normal(-8.1, 0.18)), float(normal(-2.35, 0.14)), True, float(np.clip(normal(0.18, 0.04), 0.05, 0.30)), True, True)
    if mode == BinderWorldMode.COMPOUND_FAILURE:
        return BinderHypothesis(float(np.clip(normal(0.68, 0.05), 0.52, 0.82)), float(np.clip(normal(0.22, 0.045), 0.08, 0.36)), float(normal(-6.0, 0.20)), float(normal(-0.35, 0.14)), True, float(np.clip(normal(0.62, 0.06), 0.42, 0.82)), True, True)
    if mode == BinderWorldMode.ASSAY_FAILURE:
        return BinderHypothesis(float(np.clip(normal(0.84, 0.035), 0.70, 0.95)), float(np.clip(normal(0.86, 0.035), 0.70, 0.96)), float(normal(-8.4, 0.16)), float(normal(-2.55, 0.13)), True, float(np.clip(normal(0.16, 0.035), 0.04, 0.28)), False, True)
    if mode == BinderWorldMode.MODEL_FAILURE:
        return BinderHypothesis(float(np.clip(normal(0.84, 0.035), 0.70, 0.95)), float(np.clip(normal(0.86, 0.035), 0.70, 0.96)), float(normal(-8.4, 0.16)), float(normal(-2.55, 0.13)), True, float(np.clip(normal(0.16, 0.035), 0.04, 0.28)), True, False)
    if mode == BinderWorldMode.MIXED:
        return BinderHypothesis(float(np.clip(normal(0.82, 0.04), 0.66, 0.94)), float(np.clip(normal(0.30, 0.05), 0.12, 0.42)), float(normal(-8.35, 0.18)), float(normal(-2.35, 0.15)), False, float(np.clip(normal(0.76, 0.05), 0.55, 0.91)), True, True)
    raise ValueError(f"unsupported Binder world mode: {mode}")


def _sample_v2(mode: BinderWorldMode, rng: np.random.Generator) -> BinderHypothesis:
    """Semantic V2: threshold memberships exactly match named primary mechanisms."""
    n, clip = rng.normal, np.clip
    good = lambda mean, spread, low, high: float(clip(n(mean, spread), low, high))
    good_kd = lambda mean: float(clip(n(mean, .12), -9.5, -7.15))
    good_koff = lambda mean: float(clip(n(mean, .10), -3.4, -2.15))
    bad_koff = lambda mean: float(clip(n(mean, .12), -.8, -.05))
    if mode == BinderWorldMode.SINGLE_FAILURE:
        return BinderHypothesis(good(.22, .035, .10, .32), good(.87, .025, .82, .95), good_kd(-8.1), good_koff(-2.4), True, good(.18, .03, .05, .30), True, True)
    if mode == BinderWorldMode.COMPOUND_FAILURE:
        return BinderHypothesis(good(.68, .04, .56, .82), good(.22, .045, .08, .36), good_kd(-8.1), bad_koff(-.35), True, good(.22, .035, .05, .35), True, True)
    if mode == BinderWorldMode.ASSAY_FAILURE:
        return BinderHypothesis(good(.84, .03, .72, .95), good(.87, .025, .82, .96), good_kd(-8.4), good_koff(-2.55), True, good(.16, .03, .04, .28), False, True)
    if mode == BinderWorldMode.MODEL_FAILURE:
        return BinderHypothesis(good(.84, .03, .72, .95), good(.87, .025, .82, .96), good_kd(-8.4), good_koff(-2.55), True, good(.16, .03, .04, .28), True, False)
    if mode == BinderWorldMode.MIXED:
        return BinderHypothesis(good(.82, .03, .68, .94), good(.86, .025, .80, .96), good_kd(-8.35), good_koff(-2.35), False, good(.76, .05, .55, .91), True, True)
    raise ValueError(f"unsupported Binder world mode: {mode}")
