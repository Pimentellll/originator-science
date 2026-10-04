"""Aggregate metrics (METRICS.md), reported by policy and scenario class, plus paired
same-seed comparison (G13). Nothing here fabricates results: it only summarises
CampaignEvaluation records it is given."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict

from mirage.evaluation.campaign.evaluator import CampaignEvaluation
from mirage.provenance.store import atomic_write_text, safe_id


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Rate(_Frozen):
    k: int
    n: int
    rate: float | None
    lo: float | None  # 95% Wilson interval
    hi: float | None


def wilson(k: int, n: int, z: float = 1.96) -> Rate:
    if n == 0:
        return Rate(k=0, n=0, rate=None, lo=None, hi=None)
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return Rate(k=k, n=n, rate=p, lo=max(0.0, centre - half), hi=min(1.0, centre + half))


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


class GroupSummary(_Frozen):
    n_episodes: int
    terminated: Rate
    correct: Rate  # over all episodes; ABSTAIN counts as not-correct unless it was the right call
    justified: Rate
    lucky_correct: Rate  # correct but not evidence-supported
    supported_but_wrong: Rate
    abstained: Rate
    abstention_appropriate: Rate  # among abstentions
    compound_recognized: Rate  # among compound-failure episodes with a belief
    assay_invalid_detected: Rate  # among assay-invalid episodes with a belief
    model_invalid_detected: Rate  # among model-invalid episodes with a belief
    unnecessary_redesign_episodes: Rate
    premature_aggregated_spr_episodes: Rate
    mean_budget_spent: float | None
    mean_sample_used: float | None
    mean_time_elapsed: float | None
    mean_action_count: float | None
    mean_spr_health_lost: float | None
    mean_terminal_brier: float | None
    mean_decision_calibration_error: float | None
    exploitation_flag_counts: dict[str, int]

    # Added for the real benchmark (C2).
    justified_abstention: Rate  # over all episodes
    localisation_accuracy: Rate  # molecule / assay / model / none, from the decision belief
    mechanism_precision: float | None  # micro over the 6 molecular mechanisms
    mechanism_recall: float | None
    mechanism_f1: float | None
    compound_mechanism_f1: float | None  # same, restricted to compound-failure worlds
    mean_terminal_posterior_entropy: float | None
    mean_experiments: float | None  # reliable + degraded measurements that returned a result
    correct_redesign_rate: Rate  # among redesigns
    rescued: Rate  # truth-correct SELECT of a redesigned candidate, over all episodes
    proxy_exploitation_episodes: Rate
    reward_hacking_incident_episodes: Rate


def _prf(tp: int, fp: int, fn: int) -> tuple[float | None, float | None, float | None]:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    if precision is None or recall is None or precision + recall == 0:
        return precision, recall, (0.0 if precision is not None and recall is not None else None)
    return precision, recall, 2 * precision * recall / (precision + recall)


def summarize(evals: Iterable[CampaignEvaluation]) -> GroupSummary:
    rows = list(evals)
    n = len(rows)
    abst = [e for e in rows if e.decision == "ABSTAIN"]
    comp = [e for e in rows if e.compound_failure and e.compound_recognized is not None]
    flags: Counter[str] = Counter()
    for e in rows:
        flags.update(e.exploitation_flags)

    def opt(name: str) -> list[float]:
        return [getattr(e, name) for e in rows if getattr(e, name) is not None]

    scored = [e for e in rows if e.mech_tp is not None]
    p, r, f1 = _prf(sum(e.mech_tp for e in scored), sum(e.mech_fp for e in scored), sum(e.mech_fn for e in scored))
    comp_rows = [e for e in scored if e.compound_failure]
    _, _, comp_f1 = _prf(sum(e.mech_tp for e in comp_rows), sum(e.mech_fp for e in comp_rows), sum(e.mech_fn for e in comp_rows))
    loc = [e for e in rows if e.localisation_correct is not None]
    redesigns = sum(e.redesign_count for e in rows)
    return GroupSummary(
        n_episodes=n,
        terminated=wilson(sum(e.terminated for e in rows), n),
        correct=wilson(sum(e.correct is True for e in rows), n),
        justified=wilson(sum(e.justified for e in rows), n),
        lucky_correct=wilson(sum(e.lucky_correct for e in rows), n),
        supported_but_wrong=wilson(sum(e.supported_but_wrong for e in rows), n),
        abstained=wilson(len(abst), n),
        abstention_appropriate=wilson(sum(e.abstention_quality == "appropriate" for e in abst), len(abst)),
        compound_recognized=wilson(sum(bool(e.compound_recognized) for e in comp), len(comp)),
        assay_invalid_detected=wilson(
            sum(e.assay_invalid_detected is True for e in rows),
            sum(e.assay_invalid_detected is not None for e in rows),
        ),
        model_invalid_detected=wilson(
            sum(e.model_invalid_detected is True for e in rows),
            sum(e.model_invalid_detected is not None for e in rows),
        ),
        unnecessary_redesign_episodes=wilson(sum(e.unnecessary_redesigns > 0 for e in rows), n),
        premature_aggregated_spr_episodes=wilson(sum(e.premature_aggregated_spr > 0 for e in rows), n),
        mean_budget_spent=_mean(opt("budget_spent")),
        mean_sample_used=_mean(opt("sample_used")),
        mean_time_elapsed=_mean(opt("time_elapsed")),
        mean_action_count=_mean(opt("action_count")),
        mean_spr_health_lost=_mean(opt("spr_health_lost")),
        mean_terminal_brier=_mean(opt("terminal_brier")),
        mean_decision_calibration_error=_mean(opt("decision_calibration_error")),
        exploitation_flag_counts=dict(sorted(flags.items())),
        justified_abstention=wilson(sum(e.justified_abstention for e in rows), n),
        localisation_accuracy=wilson(sum(bool(e.localisation_correct) for e in loc), len(loc)),
        mechanism_precision=p,
        mechanism_recall=r,
        mechanism_f1=f1,
        compound_mechanism_f1=comp_f1,
        mean_terminal_posterior_entropy=_mean(opt("terminal_posterior_entropy")),
        mean_experiments=_mean(opt("measurement_count")),
        correct_redesign_rate=wilson(sum(e.correct_redesigns for e in rows), redesigns),
        rescued=wilson(sum(e.rescued for e in rows), n),
        proxy_exploitation_episodes=wilson(sum("proxy_exploitation" in e.exploitation_flags for e in rows), n),
        reward_hacking_incident_episodes=wilson(sum(e.reward_hacking_incident for e in rows), n),
    )


class PolicySummary(_Frozen):
    policy_name: str
    overall: GroupSummary
    by_scenario_class: dict[str, GroupSummary]
    by_regime: dict[str, GroupSummary]
    by_archetype: dict[str, GroupSummary]


class BenchmarkSummary(_Frozen):
    """Authorised aggregate output. Contains no per-episode truth or labels."""

    benchmark_id: str
    evaluator_version: str
    seeds: tuple[int, ...]
    policies: dict[str, PolicySummary]


def _by(evals: Sequence[CampaignEvaluation], key: Callable[[CampaignEvaluation], str]) -> dict[str, list[CampaignEvaluation]]:
    groups: dict[str, list[CampaignEvaluation]] = {}
    for e in evals:
        groups.setdefault(key(e), []).append(e)
    return groups


class PairingError(ValueError):
    """Policies were not evaluated on identical seeded worlds."""


def world_key(e: CampaignEvaluation) -> tuple[str, int]:
    """A world is an (archetype, seed) pair; seeds alone may repeat across archetypes."""
    return (e.archetype, e.seed)


def assert_identical_worlds(evals: Sequence[CampaignEvaluation]) -> tuple[int, ...]:
    """Every policy must have exactly one episode per world, on the same world set, with
    the same scenario class and regime per world (G13). Returns the sorted unique seeds."""
    per_policy: dict[str, list[tuple[str, int]]] = {}
    for e in evals:
        per_policy.setdefault(e.policy_name, []).append(world_key(e))
    reference: list[tuple[str, int]] | None = None
    for policy, keys in sorted(per_policy.items()):
        if len(keys) != len(set(keys)):
            raise PairingError(f"{policy} has duplicate worlds")
        keys = sorted(keys)
        if reference is None:
            reference = keys
        elif keys != reference:
            raise PairingError(f"{policy} was run on different worlds than the other policies")
    tags: dict[tuple[str, int], set[tuple[str, str]]] = {}
    for e in evals:
        tags.setdefault(world_key(e), set()).add((e.scenario_class, e.regime))
    mismatched = [k for k, c in tags.items() if len(c) > 1]
    if mismatched:
        raise PairingError(f"worlds {mismatched} carry different tags across policies")
    return tuple(sorted({seed for _, seed in (reference or [])}))


def build_benchmark_summary(
    benchmark_id: str, evals: Sequence[CampaignEvaluation], *, require_paired: bool = True
) -> BenchmarkSummary:
    if not evals:
        raise ValueError("no evaluations to summarise")
    versions = {e.evaluator_version for e in evals}
    if len(versions) != 1:
        raise ValueError(f"mixed evaluator versions: {sorted(versions)}")
    seeds = assert_identical_worlds(evals) if require_paired else tuple(sorted({e.seed for e in evals}))
    policies = {
        policy: PolicySummary(
            policy_name=policy,
            overall=summarize(rows),
            by_scenario_class={c: summarize(g) for c, g in sorted(_by(rows, lambda e: e.scenario_class).items())},
            by_regime={c: summarize(g) for c, g in sorted(_by(rows, lambda e: e.regime).items())},
            by_archetype={c: summarize(g) for c, g in sorted(_by(rows, lambda e: e.archetype).items())},
        )
        for policy, rows in sorted(_by(evals, lambda e: e.policy_name).items())
    }
    return BenchmarkSummary(benchmark_id=benchmark_id, evaluator_version=versions.pop(), seeds=seeds, policies=policies)


class MetricDiff(_Frozen):
    """Mean of (A - B) over identical worlds with a seeded percentile-bootstrap 95% interval."""

    metric: str
    n: int
    mean_diff: float | None
    lo: float | None
    hi: float | None


class PairedComparison(_Frozen):
    policy_a: str
    policy_b: str
    n_worlds: int
    justified_a_only: int
    justified_b_only: int
    both_justified: int
    neither_justified: int
    diffs: tuple[MetricDiff, ...]
    by_regime: dict[str, tuple[MetricDiff, ...]]


# (name, extractor returning float | None). Booleans enter as 0/1.
PAIRED_METRICS: tuple[tuple[str, Callable[[CampaignEvaluation], float | None]], ...] = (
    ("correct", lambda e: float(e.correct is True)),
    ("justified", lambda e: float(e.justified)),
    ("lucky_correct", lambda e: float(e.lucky_correct)),
    ("budget_spent", lambda e: e.budget_spent),
    ("sample_used", lambda e: e.sample_used),
    ("time_elapsed", lambda e: e.time_elapsed),
    ("experiments", lambda e: float(e.measurement_count)),
    ("unnecessary_redesigns", lambda e: float(e.unnecessary_redesigns)),
    ("premature_aggregated_spr", lambda e: float(e.premature_aggregated_spr)),
    ("terminal_brier", lambda e: e.terminal_brier),
    ("terminal_posterior_entropy", lambda e: e.terminal_posterior_entropy),
)


def _bootstrap_diff(name: str, diffs: Sequence[float], seed: int, resamples: int = 2000) -> MetricDiff:
    n = len(diffs)
    if n == 0:
        return MetricDiff(metric=name, n=0, mean_diff=None, lo=None, hi=None)
    arr = np.asarray(diffs, dtype=float)
    rng = np.random.default_rng([seed, n])
    means = rng.choice(arr, size=(resamples, n), replace=True).mean(axis=1)
    return MetricDiff(
        metric=name,
        n=n,
        mean_diff=float(arr.mean()),
        lo=float(np.percentile(means, 2.5)),
        hi=float(np.percentile(means, 97.5)),
    )


def _metric_diffs(a: dict, b: dict, keys: Sequence, seed: int) -> tuple[MetricDiff, ...]:
    out = []
    for name, get in PAIRED_METRICS:
        pairs = [(get(a[k]), get(b[k])) for k in keys]
        out.append(_bootstrap_diff(name, [x - y for x, y in pairs if x is not None and y is not None], seed))
    return tuple(out)


def paired_comparison(
    evals: Sequence[CampaignEvaluation], policy_a: str, policy_b: str, *, seed: int = 0
) -> PairedComparison:
    """Differences A - B on identical (archetype, seed) worlds only."""
    assert_identical_worlds([e for e in evals if e.policy_name in (policy_a, policy_b)])
    a = {world_key(e): e for e in evals if e.policy_name == policy_a}
    b = {world_key(e): e for e in evals if e.policy_name == policy_b}
    if not a or set(a) != set(b):
        raise PairingError("policies do not cover the same worlds")
    keys = sorted(a)
    both = sum(a[k].justified and b[k].justified for k in keys)
    only_a = sum(a[k].justified and not b[k].justified for k in keys)
    only_b = sum(b[k].justified and not a[k].justified for k in keys)
    regimes = sorted({a[k].regime for k in keys})
    return PairedComparison(
        policy_a=policy_a,
        policy_b=policy_b,
        n_worlds=len(keys),
        justified_a_only=only_a,
        justified_b_only=only_b,
        both_justified=both,
        neither_justified=len(keys) - both - only_a - only_b,
        diffs=_metric_diffs(a, b, keys, seed),
        by_regime={r: _metric_diffs(a, b, [k for k in keys if a[k].regime == r], seed) for r in regimes},
    )


class RegretEstimate(_Frozen):
    """APPROXIMATE, MODEL-BASED campaign regret against a reference planner.

    utility = justified_success - cost_weight * (budget_spent / initial_budget). Regret is
    mean(utility_reference - utility_policy) over identical worlds. It measures distance to a
    strong *planner*, not to ground-truth optimality, and inherits every limitation of the
    reference policy and of the utility weights chosen here.
    """

    reference_policy: str
    policy: str
    cost_weight: float
    n_worlds: int
    mean_regret: float | None
    lo: float | None
    hi: float | None
    by_regime: dict[str, float | None]
    label: str = "approximate, model-based: distance to a reference planner, not to optimality"


def approximate_regret(
    evals: Sequence[CampaignEvaluation],
    reference_policy: str,
    policy: str,
    *,
    initial_budget: float,
    cost_weight: float = 0.2,
    seed: int = 0,
) -> RegretEstimate:
    assert_identical_worlds([e for e in evals if e.policy_name in (reference_policy, policy)])
    ref = {world_key(e): e for e in evals if e.policy_name == reference_policy}
    pol = {world_key(e): e for e in evals if e.policy_name == policy}
    if not ref or set(ref) != set(pol):
        raise PairingError("policies do not cover the same worlds")

    def utility(e: CampaignEvaluation) -> float:
        return float(e.justified) - cost_weight * e.budget_spent / initial_budget

    keys = sorted(ref)
    diffs = [utility(ref[k]) - utility(pol[k]) for k in keys]
    boot = _bootstrap_diff("regret", diffs, seed)
    by_regime = {}
    for r in sorted({ref[k].regime for k in keys}):
        sub = [utility(ref[k]) - utility(pol[k]) for k in keys if ref[k].regime == r]
        by_regime[r] = float(np.mean(sub)) if sub else None
    return RegretEstimate(
        reference_policy=reference_policy,
        policy=policy,
        cost_weight=cost_weight,
        n_worlds=len(keys),
        mean_regret=boot.mean_diff,
        lo=boot.lo,
        hi=boot.hi,
        by_regime=by_regime,
    )


class EvaluationStore:
    """Privileged on-disk store, kept apart from public records.

    Per-episode evaluations contain truth-derived fields and must never be served by the
    public API; only BenchmarkSummary (aggregates) is exposed, and only when authorised.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def save_evaluation(self, evaluation: CampaignEvaluation) -> Path:
        path = self.root / "episodes" / f"{safe_id(evaluation.episode_id)}.json"
        atomic_write_text(path, evaluation.model_dump_json(indent=2) + "\n")
        return path

    def load_evaluation(self, episode_id: str) -> CampaignEvaluation:
        path = self.root / "episodes" / f"{safe_id(episode_id)}.json"
        return CampaignEvaluation.model_validate_json(path.read_text(encoding="utf-8"))

    def save_summary(self, summary: BenchmarkSummary) -> Path:
        path = self.root / "summaries" / f"{safe_id(summary.benchmark_id)}.json"
        atomic_write_text(path, summary.model_dump_json(indent=2) + "\n")
        return path

    def load_summary(self, benchmark_id: str) -> BenchmarkSummary:
        path = self.root / "summaries" / f"{safe_id(benchmark_id)}.json"
        if not path.is_file():
            raise FileNotFoundError(benchmark_id)
        return BenchmarkSummary.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def list_summaries(self) -> list[str]:
        directory = self.root / "summaries"
        return sorted(p.stem for p in directory.glob("*.json")) if directory.is_dir() else []
