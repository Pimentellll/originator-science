import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mirage.assay.od_reader import response, x_lin
from mirage.biology.growth import richards
from mirage.config import canonical_sha256, load_prior, sample_episode
from mirage.evaluation import metrics
from mirage.evaluation.metrics import EpisodeResult, EventRecord, MeasurementAudit
from mirage.lab import tools

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_episode_llm.json"


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rec(raw: dict) -> EpisodeResult:
    return EpisodeResult.model_validate(raw)


def test_fixture_round_trips_byte_identically(rec: EpisodeResult) -> None:
    # DESIGN §18 serialisation: sorted keys, indent 2, UTF-8.
    text = json.dumps(rec.model_dump(mode="json"), sort_keys=True, indent=2, ensure_ascii=False)
    assert text + "\n" == FIXTURE.read_text(encoding="utf-8")


def test_fixture_episode_is_the_sampled_scenario_v1_episode(rec: EpisodeResult) -> None:
    prior = load_prior(ROOT / "experiments" / "configs" / "scenario_v1.json")
    assert rec.episode == sample_episode(prior, rec.episode.seed, rec.episode.condition)
    assert rec.episode.scenario_sha256 == canonical_sha256(prior)


def test_fixture_agent_and_prompt(rec: EpisodeResult) -> None:
    assert rec.agent.kind == "llm"
    assert rec.agent.prompt_version == tools.PROMPT_VERSION
    assert rec.agent.prompt_sha256 == tools.prompt_sha256()
    assert rec.llm_transcript is not None and len(rec.llm_transcript) == 3
    assert {t["response"]["model"] for t in rec.llm_transcript} == {rec.agent.model}


def test_fixture_audit_matches_noise_free_recomputation(rec: EpisodeResult) -> None:
    g, a = rec.episode.growth, rec.episode.assay
    events = {e.index: e for e in rec.events}
    for m in rec.audit:
        args = events[m.event_index].arguments
        x = float(richards(args["time_h"], **g.model_dump()))
        assert m.latent_biomass_odeq == pytest.approx(x, rel=1e-12)
        assert m.presented_biomass_odeq == pytest.approx(x / args["dilution_factor"], rel=1e-12)
        mu = float(response(m.presented_biomass_odeq, s_odeq=a.s_odeq, n=a.n))
        assert m.noise_free_reading == pytest.approx(mu, rel=1e-12)
        useful = m.presented_biomass_odeq <= x_lin(s_odeq=a.s_odeq, n=a.n, eps_lin=a.eps_lin) and (
            mu >= a.y_loq
        )
        assert m.in_useful_region == useful


def test_fixture_internal_consistency(rec: EpisodeResult) -> None:
    accepted = [e for e in rec.events if e.tool == "measure_od" and e.ok]
    assert [m.event_index for m in rec.audit] == [e.index for e in accepted]
    assert rec.scores.cost_units == sum(e.arguments["replicates"] for e in accepted)
    assert rec.diagnosis is not None and rec.status == "DIAGNOSED"
    assert rec.scores.correct == (
        (rec.diagnosis.diagnosis == "BIOMASS_ABOVE_READING")
        == (rec.episode.condition.value == "MEASUREMENT_ARTIFACT")
    )
    y = 1.0 if rec.episode.condition.value == "MEASUREMENT_ARTIFACT" else 0.0
    assert rec.scores.brier == pytest.approx((rec.diagnosis.p_biomass_above_reading - y) ** 2)
    assert [p.time_h for p in rec.passive] == list(range(19))
    assert all(p.source == "passive" and p.cost_units == 0 for p in rec.passive)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema_version="episode-result-v2"),
        lambda d: d.update(status="TIMEOUT"),
        lambda d: d.update(unexpected=1),
        lambda d: d.pop("scores"),
        lambda d: d["agent"].update(kind="human"),
        lambda d: d["audit"][0].pop("diagnostic_control"),
        lambda d: d["episode"]["growth"].update(k_odeq=-1.0),
    ],
)
def test_record_schema_rejects_invalid(raw: dict, mutate) -> None:
    d = json.loads(json.dumps(raw))
    mutate(d)
    with pytest.raises(ValidationError):
        EpisodeResult.model_validate(d)


def test_records_are_frozen(rec: EpisodeResult) -> None:
    with pytest.raises(ValidationError):
        rec.audit[0].diagnostic_control = False  # type: ignore[misc]
    assert isinstance(rec.events[0], EventRecord)
    assert isinstance(rec.audit[0], MeasurementAudit)


def test_metrics_does_not_import_anthropic() -> None:
    tree = ast.parse(Path(metrics.__file__).read_text(encoding="utf-8"))
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any(m.split(".")[0] == "anthropic" for m in names)


# ---- review fixes (fix/evaluator-consistency) -----------------------------------------------

def _diag_args(d: dict) -> dict:
    return next(e for e in d["events"] if e["tool"] == "submit_diagnosis" and e["ok"])["arguments"]


CONTRADICTIONS = {
    "status_without_diagnosis": lambda d: d.update(diagnosis=None),
    "no_diagnosis_status_with_diagnosis": lambda d: d.update(status="NO_DIAGNOSIS"),
    "api_failure_with_diagnosis": lambda d: d.update(status="API_FAILURE"),
    "diagnosis_differs_from_event": lambda d: d["diagnosis"].update(p_biomass_above_reading=0.5),
    "diagnosis_label_differs_from_event": lambda d: d["diagnosis"].update(
        diagnosis="BIOMASS_AS_READ"),
    "diagnosis_event_rejected": lambda d: d["events"][2].update(ok=False, result=None, error="x"),
    "audit_points_at_rejected_event": lambda d: d["audit"][0].update(event_index=1),
    "audit_missing": lambda d: d.update(audit=[]),
    "audit_duplicated": lambda d: d.update(audit=d["audit"] * 2),
    "audit_request_index": lambda d: d["audit"][0].update(request_index=1),
    "audit_control_contradicts_clauses": lambda d: d["audit"][0].update(diagnostic_control=False),
    "audit_recon_contradicts_clauses": lambda d: d["audit"][0].update(
        reconstruction_adequate=False),
    "audit_before_diagnosis_wrong": lambda d: d["audit"][0].update(
        before_diagnosis=False, diagnostic_control=False, reconstruction_adequate=False),
    "audit_negative_latent": lambda d: d["audit"][0].update(latent_biomass_odeq=-1.0),
    "audit_nan_reading": lambda d: d["audit"][0].update(noise_free_reading=float("nan")),
    "audit_inf_presented": lambda d: d["audit"][0].update(presented_biomass_odeq=float("inf")),
    "scores_cost": lambda d: d["scores"].update(cost_units=2),
    "scores_negative_cost": lambda d: d["scores"].update(cost_units=-3),
    "scores_control": lambda d: d["scores"].update(diagnostic_control=False, justified=False),
    "scores_justified": lambda d: d["scores"].update(justified=False),
    "scores_recon": lambda d: d["scores"].update(reconstruction_adequate=False),
    "scores_correct": lambda d: d["scores"].update(correct=False, justified=False),
    "scores_brier": lambda d: d["scores"].update(brier=0.5),
    "scores_brier_nan": lambda d: d["scores"].update(brier=float("nan")),
    "scores_calls": lambda d: d["scores"].update(measure_calls_before_diagnosis=1),
    "event_indices_gap": lambda d: d["events"][1].update(index=5),
    "event_turns_not_increasing": lambda d: d["events"][2].update(turn=1),
    "event_after_diagnosis": lambda d: d["events"].append(
        {**d["events"][0], "index": 3, "turn": 4}),
    "second_accepted_diagnosis": lambda d: d["events"].append(
        {**d["events"][2], "index": 3, "turn": 4}),
    "audit_is_diluted_disagrees_with_event": lambda d: (
        d["audit"][0].update(is_diluted=False, diagnostic_control=False,
                             reconstruction_adequate=False),
        d["scores"].update(diagnostic_control=False, justified=False,
                           reconstruction_adequate=False)),
    "audit_latent_not_presented_times_dilution": lambda d: d["audit"][0].update(
        latent_biomass_odeq=123.0),
    "scores_m5_nan": lambda d: d["scores"].update(m5_diagnosticity=float("nan")),
    "scores_m5_above_one": lambda d: d["scores"].update(m5_diagnosticity=1.5),
    "event_turns_not_positive": lambda d: [
        e.update(turn=t) for e, t in zip(d["events"], (-10, -9, -8))],
}


@pytest.mark.parametrize("name", sorted(CONTRADICTIONS))
def test_contradictory_records_rejected(raw: dict, name: str) -> None:
    d = json.loads(json.dumps(raw))
    CONTRADICTIONS[name](d)
    with pytest.raises(ValidationError):
        EpisodeResult.model_validate(d)


def test_fixture_accepted_mean_vs_noise_free(rec: EpisodeResult) -> None:
    ev = rec.events[0]
    readings = ev.result["readings"]
    assert ev.result["mean_reading"] == round(sum(readings) / len(readings), 4) == 0.4045
    assert round(rec.audit[0].noise_free_reading, 4) == 0.4104
    assert rec.diagnosis.late_biomass_estimate_od == pytest.approx(10 * 0.4045)
    assert "0.4045" in rec.diagnosis.rationale and "0.4104" not in rec.diagnosis.rationale
