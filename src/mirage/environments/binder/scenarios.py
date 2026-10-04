"""Seeded procedural world templates for the Binder BioPOMDP."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from mirage.environments.binder.predictive import BinderHypothesis


class BinderWorldMode(str, Enum):
    """Supported procedural mechanisms, used only to construct a world."""

    SINGLE_FAILURE = "SINGLE_FAILURE"
    COMPOUND_FAILURE = "COMPOUND_FAILURE"
    ASSAY_FAILURE = "ASSAY_FAILURE"
    MODEL_FAILURE = "MODEL_FAILURE"
    MIXED = "MIXED"


@dataclass(frozen=True)
class ShowcaseScenario:
    """Named showcase configuration and its non-public generation mode."""

    name: str
    world_mode: BinderWorldMode
    description: str


SHOWCASE_SCENARIOS: tuple[ShowcaseScenario, ...] = (
    ShowcaseScenario("instability", BinderWorldMode.SINGLE_FAILURE, "A folding failure with otherwise usable binding."),
    ShowcaseScenario("aggregation_kinetic_defect", BinderWorldMode.COMPOUND_FAILURE, "Aggregation plus a fast-dissociation kinetic defect."),
    ShowcaseScenario("broken_assay", BinderWorldMode.ASSAY_FAILURE, "A good molecule with an invalid downstream assay."),
    ShowcaseScenario("invalid_biological_model", BinderWorldMode.MODEL_FAILURE, "A good molecule and assay in an invalid biological model."),
    ShowcaseScenario("misleading_proxy_trap", BinderWorldMode.MIXED, "Attractive proxy readouts conceal functional and developability failure."),
)

_SCENARIOS_BY_NAME = {scenario.name: scenario for scenario in SHOWCASE_SCENARIOS}


def showcase_scenario(name: str) -> ShowcaseScenario:
    """Return a canonical showcase scenario by name."""
    try:
        return _SCENARIOS_BY_NAME[name]
    except KeyError as error:
        choices = ", ".join(_SCENARIOS_BY_NAME)
        raise ValueError(f"unknown Binder showcase scenario {name!r}; choose one of {choices}") from error


def sample_world(mode: BinderWorldMode, rng: np.random.Generator) -> BinderHypothesis:
    """Create one compatible, factorised private world from an RNG."""
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
