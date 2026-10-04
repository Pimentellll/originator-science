"""Aggregate metrics (METRICS.md), reported by policy and scenario class, plus paired
same-seed comparison (G13). Nothing here fabricates results: it only summarises
CampaignEvaluation records it is given."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

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
    )


class PolicySummary(_Frozen):
    policy_name: str
    overall: GroupSummary
    by_scenario_class: dict[str, GroupSummary]


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


def seeds_by_policy(evals: Sequence[CampaignEvaluation]) -> dict[str, list[int]]:
    return {p: sorted(e.seed for e in rows) for p, rows in _by(evals, lambda e: e.policy_name).items()}


def assert_identical_worlds(evals: Sequence[CampaignEvaluation]) -> tuple[int, ...]:
    """Every policy must have exactly one episode per seed, on the same seed set, with the
    same scenario class per seed (G13)."""
    per_policy = seeds_by_policy(evals)
    reference: list[int] | None = None
    for policy, seeds in per_policy.items():
        if len(seeds) != len(set(seeds)):
            raise PairingError(f"{policy} has duplicate seeds")
        if reference is None:
            reference = seeds
        elif seeds != reference:
            raise PairingError(f"{policy} was run on different seeds than the other policies")
    classes: dict[int, set[str]] = {}
    for e in evals:
        classes.setdefault(e.seed, set()).add(e.scenario_class)
    mismatched = [s for s, c in classes.items() if len(c) > 1]
    if mismatched:
        raise PairingError(f"seeds {mismatched} map to different scenario classes across policies")
    return tuple(reference or ())


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
        )
        for policy, rows in sorted(_by(evals, lambda e: e.policy_name).items())
    }
    return BenchmarkSummary(benchmark_id=benchmark_id, evaluator_version=versions.pop(), seeds=seeds, policies=policies)


class PairedComparison(_Frozen):
    policy_a: str
    policy_b: str
    n_seeds: int
    justified_a_only: int
    justified_b_only: int
    both_justified: int
    neither_justified: int
    mean_budget_diff_a_minus_b: float | None


def paired_comparison(evals: Sequence[CampaignEvaluation], policy_a: str, policy_b: str) -> PairedComparison:
    assert_identical_worlds([e for e in evals if e.policy_name in (policy_a, policy_b)])
    a = {e.seed: e for e in evals if e.policy_name == policy_a}
    b = {e.seed: e for e in evals if e.policy_name == policy_b}
    if not a or set(a) != set(b):
        raise PairingError("policies do not cover the same seeds")
    both = sum(a[s].justified and b[s].justified for s in a)
    only_a = sum(a[s].justified and not b[s].justified for s in a)
    only_b = sum(b[s].justified and not a[s].justified for s in a)
    return PairedComparison(
        policy_a=policy_a,
        policy_b=policy_b,
        n_seeds=len(a),
        justified_a_only=only_a,
        justified_b_only=only_b,
        both_justified=both,
        neither_justified=len(a) - both - only_a - only_b,
        mean_budget_diff_a_minus_b=_mean([a[s].budget_spent - b[s].budget_spent for s in a]),
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
