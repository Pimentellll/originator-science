"""What the scientist itself can say about how justified its current belief is.

Built from PUBLIC inputs only: the particle posterior (hypothetical worlds), the public
observation log in ``AgentState`` and, optionally, the public predictive model to rank
experiments. It is not the privileged evaluator and never sees truth; thresholds are
benchmark-default diagnostics, not biological facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from mirage.belief.acquisition import expected_information_gain
from mirage.belief.decision import TERMINAL_ORDER, TerminalUtility, correct_terminal_masks, gated_terminal_utilities
from mirage.belief.localisation import FailureLocalisation
from mirage.belief.particles import ParticleBelief
from mirage.belief.predictive import ParticlePredictiveModel
from mirage.belief.predictive_check import PredictiveCheckReport, posterior_predictive_check
from mirage.belief.schema import FAILURE_FIELDS
from mirage.core.contracts import ActionType, AgentState, ScientificAction

_SHORT = {f: f.removeprefix("p_").removesuffix("_failure").removesuffix("_invalid") for f in FAILURE_FIELDS}
_SHORT["p_assay_invalid"], _SHORT["p_model_invalid"] = "assay-invalid", "model-invalid"
_MEASUREMENTS = frozenset(
    {
        ActionType.MEASURE_STABILITY, ActionType.MEASURE_SEC, ActionType.MEASURE_SPR, ActionType.MEASURE_EPITOPE,
        ActionType.MEASURE_DEVELOPABILITY, ActionType.VALIDATE_ASSAY, ActionType.ORTHOGONAL_FUNCTION,
    }
)
_DIAGNOSTICS = _MEASUREMENTS  # every measurement/validation action is a genuine diagnostic


@dataclass(frozen=True)
class CertificateConfig:
    confidence: float = 0.85  # required posterior probability that the recommended terminal is correct
    plausible_alternative: float = 0.15  # runner-up explanation mass that counts as "still plausible"
    assay_resolved: float = 0.10  # min(p, 1-p) of assay invalidity once the control has been run
    eig_floor: float = 0.05  # nats; below this no experiment is worth running
    top_explanations: int = 3
    utility: TerminalUtility = TerminalUtility()


class CompetingExplanation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    probability: float = Field(ge=0.0, le=1.0)
    mechanisms: tuple[str, ...]


class JustificationCertificate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    posterior_entropy: float
    localisation: FailureLocalisation
    leading_explanations: tuple[CompetingExplanation, ...]
    leading_diagnosis: str
    leading_probability: float
    posterior_odds_vs_runner_up: float | None  # None when there is no runner-up mass
    alternatives_plausible: bool
    assay_tested: bool
    assay_status_resolved: bool
    model_distinguishable_from_assay: bool
    top_eig_action: ActionType | None
    top_eig: float | None
    recommended_terminal: ActionType
    terminal_correct_probability: float
    terminal_expected_utility: float
    sufficient_for_terminal: bool
    reasons: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    predictive_check: PredictiveCheckReport | None = None


def _label(pattern: int) -> tuple[str, tuple[str, ...]]:
    names = tuple(_SHORT[f] for k, f in enumerate(FAILURE_FIELDS) if pattern >> k & 1)
    return (" + ".join(names) if names else "no failure"), names


def build_certificate(
    state: AgentState,
    belief: ParticleBelief,
    *,
    model: ParticlePredictiveModel | None = None,
    available_actions: Sequence[ScientificAction] = (),
    config: CertificateConfig = CertificateConfig(),
    seed: int = 0,
    n_samples: int = 48,
    check_predictive: bool = True,
) -> JustificationCertificate:
    """Assess how justified a terminal recommendation would be right now."""
    cfg = config
    loc = belief.localisation()
    cid = state.active_candidate.candidate_id
    done = {o.action_type for o in state.observations if o.candidate_id == cid}
    any_diagnostic = bool(done & _DIAGNOSTICS)

    # --- competing causal explanations = joint failure patterns ---------------------
    dist = belief.pattern_distribution()
    order = np.argsort(-dist, kind="stable")[: max(2, cfg.top_explanations)]
    explanations = tuple(
        CompetingExplanation(label=_label(int(k))[0], probability=float(min(1.0, dist[k])), mechanisms=_label(int(k))[1])
        for k in order[: cfg.top_explanations]
        if dist[k] > 0
    )
    lead_p = float(dist[order[0]])
    run_p = float(dist[order[1]]) if len(order) > 1 else 0.0
    plausible = run_p >= cfg.plausible_alternative

    # --- assay / model identifiability ----------------------------------------------
    p_assay = loc.p_experiment_failure
    assay_tested = ActionType.VALIDATE_ASSAY in done
    assay_resolved = assay_tested and min(p_assay, 1.0 - p_assay) <= cfg.assay_resolved
    model_separable = assay_resolved and p_assay <= cfg.assay_resolved

    # --- most informative next experiment -------------------------------------------
    top_action, top_eig = None, None
    if model is not None:
        rng = np.random.default_rng(seed)
        usable = [a for a in available_actions if a.action_type in _MEASUREMENTS and a.candidate_id in (cid, None)]
        scores = {
            a.action_type: expected_information_gain(belief, model, a, n_samples=n_samples, rng=rng).eig
            for a in sorted(usable, key=lambda a: a.action_type.value)
        }
        if scores:
            top_action = max(scores, key=scores.get)
            top_eig = float(scores[top_action])

    # --- terminal recommendation ----------------------------------------------------
    masks = correct_terminal_masks(belief.failure_indicators())
    p_correct = belief.weights @ masks
    eu = gated_terminal_utilities(
        belief.weights, masks, belief.failure_indicators()[:, FAILURE_FIELDS.index("p_assay_invalid")].astype(float),
        cfg.utility, diagnostic=any_diagnostic, assay_tested=assay_tested, assay_resolved=cfg.assay_resolved,
    )
    best = max(range(len(TERMINAL_ORDER)), key=lambda k: eu[k])  # first max in TERMINAL_ORDER on ties
    rec = TERMINAL_ORDER[best]
    p_rec = float(p_correct[best])

    reasons: list[str] = []
    missing: list[str] = []
    confident = p_rec >= cfg.confidence
    if rec == ActionType.ABSTAIN:
        reasons.append("no other terminal is both supportable and confident")
        if p_assay > cfg.assay_resolved and assay_tested:
            reasons.append("the assay looks corrupted and no assay-independent evidence of candidate function exists")
        elif not assay_tested:
            missing.append("assay integrity has not been tested (run VALIDATE_ASSAY)")
        if not any_diagnostic:
            missing.append("run at least one diagnostic measurement before abstaining")
        if top_eig is not None and top_eig > cfg.eig_floor:
            missing.append(f"{top_action.value} still promises {top_eig:.2f} nats of information")
        sufficient = any_diagnostic and not missing
        if sufficient:
            reasons.append("evidence remains insufficient after diagnostics and no experiment is expected to help")
    else:
        if not confident:
            missing.append(f"P({rec.value} correct) = {p_rec:.2f} is below {cfg.confidence:.2f}")
        if plausible:
            missing.append("a major alternative explanation remains plausible")
        if rec == ActionType.MODEL_INVALID and not model_separable:
            missing.append("model invalidity is not distinguishable from assay failure")
        if rec == ActionType.SELECT and not assay_resolved:
            missing.append("assay integrity has not been established")
        if rec == ActionType.REJECT and not assay_tested:
            reasons.append("assay integrity was never tested (caution, not blocking)")
        sufficient = not missing
        if sufficient:
            reasons.append(f"P({rec.value} correct) = {p_rec:.2f} with no plausible competing explanation")

    check = posterior_predictive_check(belief, seed=seed) if check_predictive and belief.evidence else None
    if check is not None and check.verdict == "poorly_explained":
        missing.append("observations are poorly explained by the current causal model")
        sufficient = False

    return JustificationCertificate(
        posterior_entropy=belief.mechanism_entropy(),
        localisation=loc,
        leading_explanations=explanations,
        leading_diagnosis=explanations[0].label if explanations else "no failure",
        leading_probability=lead_p,
        posterior_odds_vs_runner_up=(lead_p / run_p) if run_p > 0 else None,
        alternatives_plausible=plausible,
        assay_tested=assay_tested,
        assay_status_resolved=assay_resolved,
        model_distinguishable_from_assay=model_separable,
        top_eig_action=top_action,
        top_eig=top_eig,
        recommended_terminal=rec,
        terminal_correct_probability=p_rec,
        terminal_expected_utility=float(eu[best]),
        sufficient_for_terminal=bool(sufficient),
        reasons=tuple(reasons),
        missing_evidence=tuple(missing),
        predictive_check=check,
    )
