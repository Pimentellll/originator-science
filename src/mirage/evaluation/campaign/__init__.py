"""Privileged campaign evaluation (C0) and adversarial suite (C1)."""

from mirage.evaluation.campaign.aggregate import (
    BenchmarkSummary,
    EvaluationStore,
    GroupSummary,
    PairedComparison,
    PairingError,
    assert_identical_worlds,
    build_benchmark_summary,
    paired_comparison,
    summarize,
)
from mirage.evaluation.campaign.config import EvaluatorConfig
from mirage.evaluation.campaign.evaluator import CampaignEvaluation, CampaignEvaluator, CheckResult
from mirage.evaluation.campaign.truth import FailureLabels, TruthOracle, correct_terminal_decisions

__all__ = [
    "BenchmarkSummary",
    "EvaluationStore",
    "GroupSummary",
    "PairedComparison",
    "PairingError",
    "assert_identical_worlds",
    "build_benchmark_summary",
    "paired_comparison",
    "summarize",
    "CampaignEvaluation",
    "CampaignEvaluator",
    "CheckResult",
    "EvaluatorConfig",
    "FailureLabels",
    "TruthOracle",
    "correct_terminal_decisions",
]
