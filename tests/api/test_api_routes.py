"""D1: public routes, behaviour and error hygiene (needs fastapi + httpx)."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from campaign_support import StubLabEnv, make_belief  # noqa: E402
from mirage.api import EpisodeService  # noqa: E402
from mirage.api.app import TOKEN_HEADER, create_app  # noqa: E402
from mirage.core import ActionType, ScientificAction  # noqa: E402
from mirage.evaluation.campaign import EvaluationStore  # noqa: E402
from mirage.provenance import PublicRecordStore  # noqa: E402


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


class RoguePolicy(FirstActionPolicy):
    name = "rogue"

    def choose_action(self, state, belief, available_actions):
        return ScientificAction(action_type=ActionType.SELECT, candidate_id="nope")


@pytest.fixture
def service(tmp_path):
    ids = iter(f"ep-{i}" for i in range(100))
    return EpisodeService(
        StubLabEnv,
        PublicRecordStore(tmp_path / "public"),
        belief_factory=lambda seed, state: FakeBelief(),
        policies={"first": FirstActionPolicy, "rogue": RoguePolicy},
        environment_id="stub",
        code_version="test",
        id_factory=lambda: next(ids),
    )


@pytest.fixture
def client(service):
    return TestClient(create_app(service))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "version": "mirage.api/1"}


def test_reset_returns_public_state(client):
    r = client.post("/episodes", json={"seed": 3})
    assert r.status_code == 201
    body = r.json()
    assert body["episode_id"] == "ep-0" and body["terminal"] is False
    assert body["resources"]["spr_instrument_health"] == 1.0
    assert body["belief"]["p_assay_invalid"] == 0.5
    assert {a["action_type"] for a in body["available_actions"]} >= {"MEASURE_SEC", "SELECT"}
    assert client.get("/episodes/ep-0").json() == body


def test_reset_without_body_and_validation(client):
    assert client.post("/episodes").status_code == 201
    assert client.post("/episodes", json={"seed": -1}).status_code == 422
    assert client.post("/episodes", json={"seed": 1, "hidden_truth": True}).status_code == 422
    assert client.post("/episodes", json={"policy_name": "ghost"}).status_code == 422


def test_full_episode_and_replay(client):
    client.post("/episodes", json={"seed": 4})
    for kind in ("MEASURE_SEC", "MEASURE_SPR", "REDESIGN_SOLUBILITY"):
        r = client.post("/episodes/ep-0/actions", json={"action_type": kind, "rationale": "why"})
        assert r.status_code == 200, r.text
    live = client.get("/episodes/ep-0/replay").json()
    assert live["complete"] is False and len(live["frames"]) == 3
    step = client.post("/episodes/ep-0/actions", json={"action_type": "SELECT"}).json()
    assert step["state"]["terminal"] and step["state"]["available_actions"] == []
    assert step["event"]["step"] == 3 and step["event"]["belief_before"] is not None
    replay = client.get("/episodes/ep-0/replay").json()
    assert replay["complete"] and replay["terminal_decision"]["action_type"] == "SELECT"
    assert [f["step"] for f in replay["frames"]] == [0, 1, 2, 3]
    assert replay["frames"][2]["active_candidate_id"] == replay["events"][2]["child_candidate_id"]
    assert replay["events"][0]["rationale"] == "why"


def test_replay_survives_service_restart(tmp_path, service):
    client = TestClient(create_app(service))
    client.post("/episodes", json={"seed": 4})
    client.post("/episodes/ep-0/actions", json={"action_type": "ABSTAIN"})
    fresh = EpisodeService(StubLabEnv, PublicRecordStore(tmp_path / "public"))
    again = TestClient(create_app(fresh)).get("/episodes/ep-0/replay")
    assert again.status_code == 200 and again.json() == client.get("/episodes/ep-0/replay").json()


def test_actions_after_terminal_and_unavailable_actions(client):
    client.post("/episodes", json={"seed": 1})
    client.post("/episodes/ep-0/actions", json={"action_type": "ABSTAIN"})
    assert client.post("/episodes/ep-0/actions", json={"action_type": "MEASURE_SEC"}).status_code == 409
    client.post("/episodes", json={"seed": 1})
    assert client.post("/episodes/ep-1/actions", json={"action_type": "MEASURE_SEC", "candidate_id": "ghost"}).status_code == 409
    assert client.post("/episodes/ep-1/actions", json={"action_type": "TELEPORT"}).status_code == 422
    assert client.post("/episodes/ep-1/actions", json={"action_type": "SELECT", "truth": 1}).status_code == 422


def test_resource_exhaustion_is_a_clean_conflict(client):
    client.post("/episodes", json={"seed": 1})
    codes = []
    for _ in range(12):
        codes.append(client.post("/episodes/ep-0/actions", json={"action_type": "MEASURE_SPR"}).status_code)
    assert 409 in codes and set(codes) <= {200, 409}


def test_unknown_and_unsafe_ids(client):
    assert client.get("/episodes/ep-404").status_code == 404
    assert client.get("/episodes/ep-404/replay").status_code == 404
    assert client.get("/episodes/..%2Fsecret/replay").status_code in (404, 422)
    assert client.get("/episodes/.hidden").status_code == 404


def test_recommendation(client):
    client.post("/episodes", json={"seed": 1, "policy_name": "first"})
    r = client.get("/episodes/ep-0/recommendation")
    assert r.status_code == 200 and r.json()["policy_name"] == "first"
    client.post("/episodes", json={"seed": 1})
    assert client.get("/episodes/ep-1/recommendation").status_code == 409
    client.post("/episodes", json={"seed": 1, "policy_name": "rogue"})
    assert client.get("/episodes/ep-2/recommendation").status_code == 409


def test_recommendation_requires_belief_engine(tmp_path):
    svc = EpisodeService(StubLabEnv, PublicRecordStore(tmp_path), policies={"first": FirstActionPolicy})
    c = TestClient(create_app(svc))
    state = c.post("/episodes", json={"policy_name": "first"}).json()
    assert state["belief"] is None
    assert c.get(f"/episodes/{state['episode_id']}/recommendation").status_code == 409


class ExplodingEnv(StubLabEnv):
    def step(self, action):
        raise ValueError("internal: _simulator_truth log_kd=0.123456789")


def test_environment_errors_are_not_echoed(tmp_path):
    svc = EpisodeService(ExplodingEnv, PublicRecordStore(tmp_path))
    c = TestClient(create_app(svc))
    eid = c.post("/episodes").json()["episode_id"]
    r = c.post(f"/episodes/{eid}/actions", json={"action_type": "MEASURE_SEC"})
    assert r.status_code == 409 and "0.123456789" not in r.text and "simulator" not in r.text


def test_benchmark_endpoints_are_gated(tmp_path, service):
    from campaign_support import SyntheticOracle, TraceBuilder
    from mirage.evaluation.campaign import CampaignEvaluator, FailureLabels, build_benchmark_summary

    store = EvaluationStore(tmp_path / "priv")
    b = TraceBuilder(episode_id="x-1", policy="p")
    b.decide(ActionType.ABSTAIN, make_belief())
    ev = CampaignEvaluator().evaluate(b.build(), SyntheticOracle(FailureLabels()))
    store.save_summary(build_benchmark_summary("bm-1", [ev]))

    off = TestClient(create_app(service))
    assert off.get("/benchmarks").status_code == 404
    on = TestClient(create_app(service, evaluation_store=store, aggregate_token="s3cret"))
    assert on.get("/benchmarks").status_code == 403
    assert on.get("/benchmarks", headers={TOKEN_HEADER: "wrong"}).status_code == 403
    ok = {TOKEN_HEADER: "s3cret"}
    assert on.get("/benchmarks", headers=ok).json() == ["bm-1"]
    body = on.get("/benchmarks/bm-1", headers=ok).json()
    assert body["policies"]["p"]["overall"]["n_episodes"] == 1
    assert "episode_id" not in str(body)
    assert on.get("/benchmarks/missing", headers=ok).status_code == 404
    assert on.get("/benchmarks/..%2Fx", headers=ok).status_code in (404, 422)


def test_empty_benchmark_store_lists_no_summaries_when_directory_is_missing(tmp_path, service):
    store = EvaluationStore(tmp_path / "missing" / "privileged")
    assert store.list_summaries() == []

    client = TestClient(create_app(service, evaluation_store=store, aggregate_token="s3cret"))
    response = client.get("/benchmarks", headers={TOKEN_HEADER: "s3cret"})
    assert response.status_code == 200
    assert response.json() == []


def test_openapi_exposes_no_privileged_schema(client):
    spec = client.get("/openapi.json").text.lower()
    for needle in ("simulator_truth", "privileged", "particle", "hidden_truth", "failurelabels", "campaignevaluation"):
        assert needle not in spec
