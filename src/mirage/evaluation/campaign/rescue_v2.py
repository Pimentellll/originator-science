"""Binder Rescue V2: the preregistered RESOURCE-CONSTRAINED RESCUE benchmark (spec + sampler).

Question: when exhaustive characterisation is unaffordable, does adaptive long-horizon
planning improve scientifically justified outcomes?

Everything that defines the benchmark lives here and in the files under
``experiments/preregistration/binder_rescue_v2/``. They are hash-locked in
``PREREGISTRATION.json`` and committed BEFORE any V2 policy is evaluated. Changing any of it
creates a new version; it never edits V2.

Hidden worlds are exactly the V1 worlds for the same seed: only the *initial public
resources* change, drawn from an RNG that is independent of the world RNG.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from mirage.core import ResourceState
from mirage.environments.binder import SHOWCASE_SCENARIOS, BinderBioPOMDP
from mirage.evaluation.campaign.harness import ARCHETYPE_TAGS, Archetype, World
from mirage.evaluation.campaign.privileged_binder import BinderPrivilegedOracle, LabelRules

SPEC_VERSION = "binder-rescue-v2"
# Entropy namespace for the resource draws; fixed, unrelated to any world or policy RNG.
RESOURCE_ENTROPY = 0x52455343  # "RESC"

# Documented action costs of core's BinderBioPOMDP (budget, sample, time). A test asserts
# these equal core's private cost table so drift is detected.
ACTION_COSTS: dict[str, tuple[float, float, float]] = {
    "MEASURE_STABILITY": (1.0, 0.5, 0.5),
    "MEASURE_SEC": (1.0, 0.5, 0.5),
    "MEASURE_SPR": (2.0, 1.0, 1.0),
    "MEASURE_EPITOPE": (1.0, 0.4, 0.5),
    "MEASURE_DEVELOPABILITY": (1.0, 0.4, 0.5),
    "VALIDATE_ASSAY": (0.75, 0.1, 0.25),
    "ORTHOGONAL_FUNCTION": (1.5, 0.25, 0.75),
    "REDESIGN_STABILITY": (2.0, 1.0, 1.0),
    "REDESIGN_SOLUBILITY": (2.0, 1.0, 1.0),
    "REDESIGN_INTERFACE": (2.0, 1.0, 1.0),
}
FULL_FUNNEL = (
    "MEASURE_STABILITY", "MEASURE_SEC", "MEASURE_SPR", "MEASURE_EPITOPE",
    "MEASURE_DEVELOPABILITY", "VALIDATE_ASSAY", "ORTHOGONAL_FUNCTION",
)  # FixedPipeline's sequence


def funnel_cost() -> tuple[float, float]:
    return (
        sum(ACTION_COSTS[a][0] for a in FULL_FUNNEL),
        sum(ACTION_COSTS[a][1] for a in FULL_FUNNEL),
    )  # (8.25, 3.15)


@dataclass(frozen=True)
class Stratum:
    """Uniform ranges for the initial public resources. Equal bounds mean a constant."""

    name: str
    budget: tuple[float, float]
    sample: tuple[float, float]
    spr_health: tuple[float, float]
    rationale: str


STRATA: dict[str, Stratum] = {
    "low": Stratum(
        "low", (2.5, 4.5), (1.0, 2.0), (0.60, 1.0),
        "A small or under-supplied lab: roughly 30-55% of the budget and 30-65% of the sample the "
        "7-assay funnel needs. The funnel is infeasible in every draw. The instrument may already be worn "
        "(health < 0.70 degrades every SPR readout in core).",
    ),
    "medium": Stratum(
        "medium", (6.0, 10.0), (2.5, 5.0), (0.80, 1.0),
        "A constrained lab: the funnel is affordable only in some draws and leaves little or no room "
        "for redesign.",
    ),
    "high": Stratum(
        "high", (10.0, 14.0), (5.0, 9.0), (1.0, 1.0),
        "A well-supplied lab (brackets V1's 12.0 / 8.0): the funnel is always affordable with room for "
        "about one redesign. FixedPipeline is expected to perform well here.",
    ),
}
STRATUM_ORDER = ("low", "medium", "high")

# Held out of the spec on purpose (see the preregistration): core has no public deadline, so
# simulated time is not a binding, observable resource and is not randomised.
UNCONSTRAINED = {"simulated_time": "core exposes no deadline or time_remaining; time only accumulates"}

SEEDS = {
    "development": list(range(1100, 1150)),   # policy tuning allowed here only
    "held_out": list(range(60000, 60050)),    # evaluation only, all 50 are used, no extension
    "train_reserved_inclusive": [100_000, 199_999],  # learned policies train here only
}
V1_SEEDS = {"development": list(range(1000, 1050)), "held_out": list(range(50000, 50100))}


def sample_resources(seed: int, stratum: str) -> ResourceState:
    """Initial public resources for world ``seed`` in ``stratum``. Pure and deterministic; the
    draw order is fixed (budget, sample, SPR health) and values are rounded to 2 decimals."""
    s = STRATA[stratum]
    rng = np.random.default_rng([RESOURCE_ENTROPY, int(seed), STRATUM_ORDER.index(stratum)])
    draws = {
        "budget": rng.uniform(*s.budget),
        "sample": rng.uniform(*s.sample),
        "health": rng.uniform(*s.spr_health) if s.spr_health[0] < s.spr_health[1] else s.spr_health[0],
    }
    return ResourceState(
        budget_remaining=round(float(draws["budget"]), 2),
        sample_remaining=round(float(draws["sample"]), 2),
        simulated_time=0.0,
        spr_instrument_health=round(float(draws["health"]), 2),
    )


class ResourceConstrainedBinder(BinderBioPOMDP):
    """BinderBioPOMDP whose episode starts from stratum-sampled resources.

    Interim wrapper: core has no ``initial_resources`` option, so after the unchanged
    ``reset`` it replaces the initial resource state. It never touches hidden state or any RNG
    that the world or the observation noise uses (a test asserts the hidden world and the
    observation stream are identical to the plain environment's). Core should adopt an official
    constructor argument and this class should then be retired.
    """

    def __init__(self, world_mode, stratum: str) -> None:
        if stratum not in STRATA:
            raise ValueError(f"unknown stratum {stratum!r}")
        self._stratum = stratum
        super().__init__(world_mode)

    def reset(self, seed: int | None = None):
        state = super().reset(seed)
        if seed is None:  # construction-time reset inside BinderBioPOMDP.__init__
            return state
        self._resources = sample_resources(seed, self._stratum)
        return self.agent_state()


class RescueWorldSource:
    """Every (archetype, seed) world is played in all three strata (fully crossed)."""

    def __init__(self, rules: LabelRules | None = None) -> None:
        self.rules = rules or LabelRules()
        self._names = {s.name: s for s in SHOWCASE_SCENARIOS}

    def worlds(self, archetype: Archetype, seeds: Sequence[int]) -> list[World]:
        scenario = self._names[archetype.value]
        scenario_class, _ = ARCHETYPE_TAGS[archetype]
        out = []
        for seed in seeds:
            for stratum in STRATUM_ORDER:
                out.append(
                    World(
                        seed=seed,
                        archetype=f"{archetype.value}.{stratum}",
                        scenario_class=scenario_class.value,
                        regime=stratum,
                        make_env=lambda mode=scenario.world_mode, st=stratum: ResourceConstrainedBinder(mode, st),
                        make_oracle=lambda env: BinderPrivilegedOracle(env, self.rules),
                    )
                )
        return out


# --------------------------------------------------------------- feasibility
def funnel_affordable_fraction(stratum: str, n: int = 200_000, seed: int = 0) -> float:
    """Fraction of resource draws in which the whole fixed funnel is affordable.
    Property of the sampler only; no policy is involved."""
    s = STRATA[stratum]
    rng = np.random.default_rng([seed, STRATUM_ORDER.index(stratum)])
    b = rng.uniform(*s.budget, n)
    m = rng.uniform(*s.sample, n)
    fb, fs = funnel_cost()
    return float(np.mean((b >= fb) & (m >= fs)))


def minimal_justified_costs() -> dict[str, dict[str, float | str]]:
    """Structural minimum (budget, sample) the evaluator's evidence rules require before each
    terminal decision CAN be justified, ignoring belief thresholds (which only add cost).
    Derived from campaign-eval/1 ``select_required_actions`` and the REJECT / MODEL_INVALID /
    ABSTAIN support checks."""
    c = ACTION_COSTS

    def tot(*names: str) -> tuple[float, float]:
        return (sum(c[n][0] for n in names), sum(c[n][1] for n in names))

    select_ok = tot("MEASURE_STABILITY", "MEASURE_SEC", "MEASURE_SPR", "MEASURE_EPITOPE", "MEASURE_DEVELOPABILITY", "VALIDATE_ASSAY")
    select_broken = tot("MEASURE_STABILITY", "MEASURE_SEC", "MEASURE_SPR", "MEASURE_EPITOPE", "MEASURE_DEVELOPABILITY", "VALIDATE_ASSAY", "ORTHOGONAL_FUNCTION")
    reject = tot("VALIDATE_ASSAY", "MEASURE_EPITOPE")  # cheapest directly assayed factor + control
    model = tot("VALIDATE_ASSAY", "MEASURE_EPITOPE")
    abstain = tot("VALIDATE_ASSAY", "MEASURE_EPITOPE")  # >= 2 reliable measurements
    return {
        "SELECT (valid assay)": {"budget": select_ok[0], "sample": select_ok[1]},
        "SELECT (broken assay, needs orthogonal support)": {"budget": select_broken[0], "sample": select_broken[1]},
        "REJECT (cheapest evidenced factor)": {"budget": reject[0], "sample": reject[1]},
        "MODEL_INVALID (structural minimum only)": {"budget": model[0], "sample": model[1]},
        "ABSTAIN (>=2 measurements)": {"budget": abstain[0], "sample": abstain[1]},
    }


def select_justifiable_fraction(stratum: str, n: int = 200_000, seed: int = 0) -> dict[str, float]:
    """Fraction of draws in which a justified SELECT is even structurally possible."""
    s = STRATA[stratum]
    rng = np.random.default_rng([seed, 7, STRATUM_ORDER.index(stratum)])
    b = rng.uniform(*s.budget, n)
    m = rng.uniform(*s.sample, n)
    need = minimal_justified_costs()
    out = {}
    for key in ("SELECT (valid assay)", "SELECT (broken assay, needs orthogonal support)"):
        out[key] = float(np.mean((b >= need[key]["budget"]) & (m >= need[key]["sample"])))
    return out


# ------------------------------------------------------------------- spec
def spec_dict() -> dict:
    fb, fs = funnel_cost()
    return {
        "spec_version": SPEC_VERSION,
        "question": "When exhaustive characterisation is unaffordable, does adaptive long-horizon planning "
        "improve scientifically justified outcomes?",
        "design": "every (archetype, seed) world is played at all three resource strata (fully crossed)",
        "archetypes": [a.value for a in Archetype],
        "strata": {
            k: {"budget": list(v.budget), "sample": list(v.sample), "spr_health": list(v.spr_health), "rationale": v.rationale}
            for k, v in STRATA.items()
        },
        "sampling": {
            "distribution": "independent uniform within each range, rounded to 2 decimals",
            "rng": f"numpy default_rng([{RESOURCE_ENTROPY}, seed, stratum_index]) with stratum_index low=0, medium=1, high=2",
            "draw_order": ["budget", "sample", "spr_health"],
            "independent_of_world_rng": True,
        },
        "unconstrained": UNCONSTRAINED,
        "action_costs_budget_sample_time": ACTION_COSTS,
        "full_funnel_cost": {"budget": fb, "sample": fs, "sequence": list(FULL_FUNNEL)},
        "seeds": SEEDS,
        "episodes_per_policy": len(Archetype) * len(STRATA) * len(SEEDS["held_out"]),
        "worlds_per_stratum": len(Archetype) * len(SEEDS["held_out"]),
        "evaluator": {"version": "campaign-eval/1", "label_rules": LabelRules().as_dict()},
        "belief": {"n_particles": 512, "prior": "binder_benchmark.PRIOR_PARAMS (unchanged from V1)"},
    }


def spec_sha256() -> str:
    return hashlib.sha256(json.dumps(spec_dict(), sort_keys=True).encode()).hexdigest()


# ------------------------------------------------------------------- lock
PREREG_DIR = "experiments/preregistration/binder_rescue_v2"
# Files whose bytes define V2 or its scoring. Any change creates a new version.
LOCKED_FILES = (
    "src/mirage/evaluation/campaign/rescue_v2.py",
    "src/mirage/evaluation/campaign/truth.py",
    "src/mirage/evaluation/campaign/evidence.py",
    "src/mirage/evaluation/campaign/evaluator.py",
    "src/mirage/evaluation/campaign/config.py",
    "src/mirage/evaluation/campaign/privileged_binder.py",
    "src/mirage/evaluation/campaign/aggregate.py",
    "docs/evaluation/BINDER_RESCUE_V2.md",
    f"{PREREG_DIR}/spec.json",
    f"{PREREG_DIR}/seed_manifest.json",
)


def compute_lock(repo_root) -> dict:
    from pathlib import Path

    root = Path(repo_root)
    return {
        "spec_version": SPEC_VERSION,
        "spec_sha256": spec_sha256(),
        "files": {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in LOCKED_FILES},
    }


def verify_lock(repo_root) -> list[str]:
    """Differences between the committed lock and the files now on disk (empty means intact)."""
    from pathlib import Path

    root = Path(repo_root)
    lock = json.loads((root / PREREG_DIR / "PREREGISTRATION.json").read_text())["lock"]
    now = compute_lock(root)
    problems = []
    if lock["spec_sha256"] != now["spec_sha256"]:
        problems.append("spec_dict() no longer matches the locked spec")
    for name, digest in lock["files"].items():
        if now["files"].get(name) != digest:
            problems.append(f"{name} changed since preregistration")
    return problems
