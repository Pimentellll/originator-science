"""Particle belief engine over factorised latent scientific worlds."""

from mirage.belief.acquisition import EIGEstimate, expected_information_gain, sample_sources
from mirage.belief.decision import TERMINAL_ORDER, TerminalUtility, correct_terminal_masks, terminal_expected_utilities
from mirage.belief.justification import CertificateConfig, CompetingExplanation, JustificationCertificate, build_certificate
from mirage.belief.localisation import FailureLocalisation
from mirage.belief.particles import (
    binary_entropy,
    DegenerateBeliefError,
    ParticleBelief,
    TransitionKernel,
    UpdateInfo,
)
from mirage.belief.predictive import ParticlePredictiveModel
from mirage.belief.predictive_check import (
    ObservationSurprise,
    PredictiveCheckReport,
    posterior_predictive_check,
    predictive_surprise,
    summarise_surprises,
)
from mirage.belief.priors import (
    ConditionedPrior,
    Factor,
    IndependentPrior,
    MixturePrior,
    Prior,
    bernoulli,
    uniform,
)
from mirage.belief.resampling import stratified_resample, systematic_resample
from mirage.belief.schema import (
    BINDER_SCHEMA_PROVISIONAL,
    FAILURE_FIELDS,
    FailureRule,
    LatentSchema,
)
from mirage.belief.summary import BeliefSummary

__all__ = [
    "BINDER_SCHEMA_PROVISIONAL",
    "BeliefSummary",
    "CertificateConfig",
    "CompetingExplanation",
    "JustificationCertificate",
    "ObservationSurprise",
    "PredictiveCheckReport",
    "build_certificate",
    "posterior_predictive_check",
    "predictive_surprise",
    "summarise_surprises",
    "FailureLocalisation",
    "TERMINAL_ORDER",
    "TerminalUtility",
    "correct_terminal_masks",
    "terminal_expected_utilities",
    "ConditionedPrior",
    "DegenerateBeliefError",
    "EIGEstimate",
    "FAILURE_FIELDS",
    "Factor",
    "FailureRule",
    "IndependentPrior",
    "LatentSchema",
    "MixturePrior",
    "ParticleBelief",
    "ParticlePredictiveModel",
    "Prior",
    "TransitionKernel",
    "UpdateInfo",
    "bernoulli",
    "binary_entropy",
    "expected_information_gain",
    "sample_sources",
    "stratified_resample",
    "systematic_resample",
    "uniform",
]
