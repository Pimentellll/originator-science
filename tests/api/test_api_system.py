"""System routes (/version, /policies, /scenarios, /diagnostics), scenario selection, and the
token-gated terminal verdict, all against the real receptor-binder service."""

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from mirage.api.app import create_app  # noqa: E402
from mirage.environments.binder import BinderWorldMode  # noqa: E402
from mirage.environments.binder.scenarios import BinderScenarioVersion  # noqa: E402
from mirage.integration import make_receptor_binder_service  # noqa: E402
from mirage.integration.catalogue import receptor_binder_catalogue  # noqa: E402
from mirage.provenance import PublicRecordStore  # noqa: E402

TOKEN = "unit-test-token"
HEADERS = {"X-Mirage-Eval-Token": TOKEN}
WORLD_WORDS = ("compound_failure", "single_failure", "assay_failure", "model_failure", "world_mode", "aggregation_kinetic_defect", "broken_assay")


@pytest.fixture
def client(tmp_path):
    version = BinderScenarioVersion.SEMANTICS_V2
    service = make_receptor_binder_service(PublicRecordStore(tmp_path), scenario_version=version, code_version="testsha")
    catalogue = receptor_binder_catalogue(service, BinderWorldMode.COMPOUND_FAILURE, version)
    return TestClient(create_app(service, aggregate_token=TOKEN, catalogue=catalogue))


def play_with_actions(client, seed=9, policy="rescue_planner", **extra):
    state = client.post("/episodes", json={"seed": seed, "policy_name": policy, **extra})
    assert state.status_code == 201, state.text
    eid = state.json()["episode_id"]
    actions = []
    for _ in range(16):
        action = client.get(f"/episodes/{eid}/recommendation").json()["action"]
        actions.append(action["action_type"])
        step = client.post(f"/episodes/{eid}/actions", json=action).json()
        if step["state"]["terminal"]:
            return eid, actions
    raise AssertionError("episode did not terminate")


def play(client, seed=9, policy="rescue_planner", **extra):
    eid, _ = play_with_actions(client, seed=seed, policy=policy, **extra)
    return eid


def test_version_is_safe_and_reports_semantics_default(client):
    body = client.get("/version").json()
    assert body["scenario_semantics_default"] == "SEMANTICS_V2"
    assert set(body["scenario_semantics_available"]) == {"BASELINE_V1", "SEMANTICS_V2"}
    assert body["git_sha"] and body["api_version"] == "mirage.api/1"
    assert "/" not in body["git_sha"] and "home" not in json.dumps(body).lower()


def test_policy_catalogue_lists_only_wired_policies_as_available(client):
    rows = {p["name"]: p for p in client.get("/policies").json()}
    for name in ("rescue_planner", "greedy_eig", "fixed_pipeline", "random", "lookahead"):
        assert rows[name]["available"] is True
        client.post("/episodes", json={"seed": 1, "policy_name": name}).raise_for_status()
    for name in ("ppo",):
        assert rows[name]["available"] is False and rows[name]["reason"]
        assert client.post("/episodes", json={"seed": 1, "policy_name": name}).status_code == 422


def test_lookahead_reaches_a_terminal_decision_deterministically(client):
    _, first = play_with_actions(
        client,
        policy="lookahead",
        scenario="aggregation_kinetic_defect",
        scenario_version="SEMANTICS_V2",
    )
    _, second = play_with_actions(
        client,
        policy="lookahead",
        scenario="aggregation_kinetic_defect",
        scenario_version="SEMANTICS_V2",
    )
    assert first == second
    assert first[-1] in {"SELECT", "REJECT", "MODEL_INVALID", "ABSTAIN"}


def test_scenario_selection_is_recorded_as_version_only_never_as_world(client):
    eid = play(client, scenario="broken_assay", scenario_version="BASELINE_V1")
    replay = client.get(f"/episodes/{eid}/replay").json()
    assert replay["environment_id"] == "RECEPTOR_BINDER_RESCUE/BASELINE_V1"
    assert replay["code_version"] == "testsha" and replay["seed"] == 9 and replay["policy_name"]
    text = json.dumps(replay).lower()
    assert not [w for w in WORLD_WORDS if w in text]


def test_default_episode_is_tagged_with_default_semantics(client):
    eid = play(client)
    assert client.get(f"/episodes/{eid}/replay").json()["environment_id"] == "RECEPTOR_BINDER_RESCUE/SEMANTICS_V2"


@pytest.mark.parametrize("extra", [{"scenario": "nope"}, {"scenario_version": "V99"}, {"scenario": "bad id!"}])
def test_unknown_scenario_is_refused(client, extra):
    assert client.post("/episodes", json={"seed": 1, **extra}).status_code == 422


def test_scenarios_catalogue_has_five_worlds(client):
    assert {s["id"] for s in client.get("/scenarios").json()} == {
        "instability", "aggregation_kinetic_defect", "broken_assay", "invalid_biological_model", "misleading_proxy_trap",
    }


def test_diagnostics_runs_real_self_checks(client):
    body = client.get("/diagnostics").json()
    by_name = {c["name"]: c for c in body["checks"]}
    assert body["status"] == "ok", body
    for name in ("environment", "deterministic_smoke", "record_replay", "leak_guard"):
        assert by_name[name]["status"] == "pass"


def test_verdict_requires_token_and_terminal_episode(client):
    state = client.post("/episodes", json={"seed": 9, "policy_name": "rescue_planner"}).json()
    eid = state["episode_id"]
    assert client.get(f"/benchmarks/episodes/{eid}").status_code == 403
    assert client.get(f"/benchmarks/episodes/{eid}", headers=HEADERS).status_code == 409
    done = play(client)
    verdict = client.get(f"/benchmarks/episodes/{done}", headers=HEADERS)
    assert verdict.status_code == 200
    body = verdict.json()
    assert {"decision", "correct", "justified", "justification_checks"} <= body.keys()
    leaked = {"scenario_class", "archetype", "regime", "true_level", "assay_invalid_truth", "model_invalid_truth"}
    assert not leaked & body.keys()


def test_rescue_planner_validates_a_doubted_assay_before_semantics_v2_verdict(client):
    eid, actions = play_with_actions(
        client,
        scenario="aggregation_kinetic_defect",
        scenario_version="SEMANTICS_V2",
    )
    assert actions.index("VALIDATE_ASSAY") < len(actions) - 1
    verdict = client.get(f"/benchmarks/episodes/{eid}", headers=HEADERS).json()
    assert verdict["correct"] is True
    assert verdict["justified"] is True


def test_rescue_planner_baseline_v1_action_sequence_is_unchanged(client):
    eid, actions = play_with_actions(
        client,
        scenario="aggregation_kinetic_defect",
        scenario_version="BASELINE_V1",
    )
    assert actions == ["MEASURE_SEC", "REDESIGN_SOLUBILITY", "MEASURE_SPR", "REJECT"]
    verdict = client.get(f"/benchmarks/episodes/{eid}", headers=HEADERS).json()
    assert verdict["correct"] is True
    assert verdict["justified"] is True


def test_verdict_is_off_without_a_token(tmp_path):
    service = make_receptor_binder_service(PublicRecordStore(tmp_path))
    client = TestClient(create_app(service))
    eid = play(client)
    assert client.get(f"/benchmarks/episodes/{eid}", headers=HEADERS).status_code == 404


def test_verdict_does_not_leak_through_public_routes(client):
    eid = play(client)
    for path in (f"/episodes/{eid}", f"/episodes/{eid}/replay", "/version", "/policies", "/scenarios", "/diagnostics"):
        body = client.get(path)
        assert body.status_code == 200
        assert '"correct"' not in body.text and '"justified"' not in body.text


def test_scenarios_flag_exactly_the_server_default(client):
    defaults = [s["id"] for s in client.get("/scenarios").json() if s["is_default"]]
    assert defaults == ["aggregation_kinetic_defect"]
