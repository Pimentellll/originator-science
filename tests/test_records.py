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
        (rec.diagnosis.diagnosis == "GROWTH_CONTINUED")
        == (rec.episode.condition.value == "MEASUREMENT_ARTIFACT")
    )
    y = 1.0 if rec.episode.condition.value == "MEASUREMENT_ARTIFACT" else 0.0
    assert rec.scores.brier == pytest.approx((rec.diagnosis.p_growth_continued - y) ** 2)
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
