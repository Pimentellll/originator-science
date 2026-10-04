"""Growth benchmark routes follow the public/evaluator trust boundary."""

import json
from pathlib import Path

import pytest
from campaign_support import StubLabEnv, make_belief
from fastapi.testclient import TestClient
from test_ui_api import C1_RUN, C2_RUN, GS_RUN, PB_RUN

from mirage.api import EpisodeService
from mirage.api.app import TOKEN_HEADER, create_app
from mirage.provenance import PublicRecordStore, find_privileged_fields
from mirage.ui import api as growth_api

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments" / "results"
TOKEN = "t"
TOKEN_HEADERS = {TOKEN_HEADER: TOKEN}


class FakeBelief:
    def __init__(self):
        self.n = 0

    def summary(self):
        return make_belief(posterior_entropy=1.0 / (1 + self.n))

    def update(self, action, result):
        self.n += 1


class FirstActionPolicy:
    name = "first"

    def reset(self, seed=None):
        pass

    def choose_action(self, state, belief, available_actions):
        return available_actions[0]


@pytest.fixture
def service(tmp_path):
    ids = iter(f"ep-{i}" for i in range(100))
    return EpisodeService(
        StubLabEnv,
        PublicRecordStore(tmp_path / "public"),
        belief_factory=lambda seed, state: FakeBelief(),
        policies={"first": FirstActionPolicy},
        environment_id="stub",
        code_version="test",
        id_factory=lambda: next(ids),
    )


@pytest.fixture
def growth_client(service):
    return TestClient(
        create_app(
            service,
            growth_results_root=RESULTS,
            aggregate_token=TOKEN,
        )
    )


def test_growth_routes_require_aggregate_token(service):
    disabled = TestClient(create_app(service, growth_results_root=RESULTS))
    response = disabled.get("/benchmarks/growth/runs")
    assert response.status_code == 404
    assert response.json() == {"detail": "aggregate results are not enabled"}

    empty_token = TestClient(
        create_app(
            service,
            growth_results_root=RESULTS,
            aggregate_token="",
        )
    )
    assert empty_token.get("/benchmarks/growth/runs").status_code == 403

    enabled = TestClient(
        create_app(
            service,
            growth_results_root=RESULTS,
            aggregate_token=TOKEN,
        )
    )
    assert enabled.get("/benchmarks/growth/runs").status_code == 403
    assert (
        enabled.get(
            "/benchmarks/growth/runs",
            headers={TOKEN_HEADER: "wrong"},
        ).status_code
        == 403
    )
    assert (
        enabled.get(
            "/benchmarks/growth/runs", headers=TOKEN_HEADERS
        ).status_code
        == 200
    )


def test_growth_runs_match_ui_api(growth_client):
    response = growth_client.get(
        "/benchmarks/growth/runs", headers=TOKEN_HEADERS
    )
    assert response.status_code == 200
    assert response.json() == growth_api.list_runs(RESULTS)


def test_growth_episode_contains_derived_measurements_and_diagnosis(
    growth_client,
):
    response = growth_client.get(
        f"/benchmarks/growth/runs/{C1_RUN}/episodes/s500001-MA",
        headers=TOKEN_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["derived"]["measurements"]) == 3
    assert body["diagnosis"]["diagnosis"] == "BIOMASS_ABOVE_READING"


def test_growth_grid_has_opus_sonnet_and_baselines_in_order(growth_client):
    response = growth_client.get(
        "/benchmarks/growth/grid?matrix=strong", headers=TOKEN_HEADERS
    )
    assert response.status_code == 200
    assert [column["run_id"] for column in response.json()["columns"]] == [
        C1_RUN,
        C2_RUN,
        GS_RUN,
        PB_RUN,
    ]
    assert (
        growth_client.get(
            "/benchmarks/growth/grid", headers=TOKEN_HEADERS
        ).status_code
        == 400
    )
    assert (
        growth_client.get(
            "/benchmarks/growth/grid?matrix=", headers=TOKEN_HEADERS
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "condition",
    ["BIOLOGICAL_PLATEAU", "MEASUREMENT_ARTIFACT"],
)
def test_public_sandbox_flow_does_not_leak_truth(growth_client, condition):
    created = growth_client.post(
        "/growth/sandbox", json={"seed": 123, "condition": condition}
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    _assert_public(created.json(), condition)

    measured = growth_client.post(
        f"/growth/sandbox/{session_id}/measure",
        json={"time_h": 18, "dilution_factor": 10, "replicates": 2},
    )
    assert measured.status_code == 200
    _assert_public(measured.json(), condition)

    diagnosed = growth_client.post(
        f"/growth/sandbox/{session_id}/diagnose",
        json={
            "diagnosis": "BIOMASS_ABOVE_READING",
            "p_biomass_above_reading": 0.9,
            "late_biomass_estimate_od": None,
            "rationale": "The evidence supports elevated biomass.",
        },
    )
    assert diagnosed.status_code == 200
    assert diagnosed.json()["status"] == "DIAGNOSED"
    assert set(diagnosed.json()) == {"events", "diagnosis", "status", "passive"}
    _assert_public(diagnosed.json(), condition)

    verdict = growth_client.get(
        f"/benchmarks/growth/sandbox/{session_id}/verdict",
        headers=TOKEN_HEADERS,
    )
    assert verdict.status_code == 200
    assert verdict.json()["reveal"]["condition"] == condition
    assert "scores" in verdict.json()


def _assert_public(payload, condition):
    assert find_privileged_fields(payload) == []
    assert condition not in json.dumps(payload)


def test_growth_sandbox_errors_and_disabled_routes(service, growth_client):
    created = growth_client.post(
        "/growth/sandbox",
        json={"seed": 123, "condition": "BIOLOGICAL_PLATEAU"},
    )
    session_id = created.json()["session_id"]
    before_diagnosis = growth_client.get(
        f"/benchmarks/growth/sandbox/{session_id}/verdict",
        headers=TOKEN_HEADERS,
    )
    assert before_diagnosis.status_code == 409
    assert before_diagnosis.json() == {
        "detail": "diagnose the sandbox session first"
    }

    evaluation_seed = growth_client.post(
        "/growth/sandbox",
        json={"seed": 500001, "condition": "BIOLOGICAL_PLATEAU"},
    )
    assert evaluation_seed.status_code == 400

    unknown = growth_client.post(
        "/growth/sandbox/unknown-session/measure",
        json={"time_h": 18, "dilution_factor": 10, "replicates": 1},
    )
    assert unknown.status_code == 404

    disabled = TestClient(create_app(service, aggregate_token=TOKEN))
    assert disabled.get("/benchmarks/growth/runs").status_code == 404
    assert (
        disabled.post(
            "/growth/sandbox",
            json={"seed": 123, "condition": "BIOLOGICAL_PLATEAU"},
        ).status_code
        == 404
    )


def test_growth_post_requires_json_object(growth_client):
    headers = {"Content-Type": "application/json"}
    malformed = growth_client.post(
        "/growth/sandbox", content="{", headers=headers
    )
    non_object = growth_client.post("/growth/sandbox", json=[])
    assert malformed.status_code == 400
    assert non_object.status_code == 400


def test_growth_autoplay_is_gated_and_returns_justified_good_scientist(
    growth_client,
):
    created = growth_client.post(
        "/growth/sandbox",
        json={"seed": 0, "condition": "BIOLOGICAL_PLATEAU"},
    )
    session_id = created.json()["session_id"]
    diagnosed = growth_client.post(
        f"/growth/sandbox/{session_id}/diagnose",
        json={
            "diagnosis": "BIOMASS_ABOVE_READING",
            "p_biomass_above_reading": 0.9,
            "late_biomass_estimate_od": None,
            "rationale": "The evidence supports elevated biomass.",
        },
    )
    assert diagnosed.status_code == 200

    path = f"/benchmarks/growth/sandbox/{session_id}/autoplay"
    assert growth_client.post(path, json={"agent": "good_scientist"}).status_code == 403
    response = growth_client.post(
        path,
        json={"agent": "good_scientist"},
        headers=TOKEN_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["scores"]["justified"] is True
