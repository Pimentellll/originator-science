"""Aggressive nested-serialization leakage tests for the public API (G2, ADR 0007)."""

import json
import random

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from campaign_support import TRUTH_CANARY, StubLabEnv, make_belief  # noqa: E402
from mirage.api import EpisodeService, dto  # noqa: E402
from mirage.api.app import create_app  # noqa: E402
from mirage.core import Candidate, ScientificAction  # noqa: E402
from mirage.provenance import (  # noqa: E402
    PublicRecordStore,
    find_privileged_fields,
    validate_belief_payload,
)

NEEDLES = (str(TRUTH_CANARY), "0.123456789", "_simulator_truth", "_privileged_state", "aggregated", "secret_affinity")


def walk_text(client, ids):
    """Every public GET for the episode, plus error paths, as raw text."""
    texts = []
    for eid in ids:
        for path in ("", "/actions", "/replay", "/recommendation"):
            texts.append(client.get(f"/episodes/{eid}{path}").text)
    texts += [client.get(p).text for p in ("/openapi.json", "/docs", "/health", "/episodes/none", "/nope")]
    return texts


def assert_clean(texts):
    for text in texts:
        for needle in NEEDLES:
            assert needle not in text, f"{needle!r} leaked"
        try:
            payload = json.loads(text)
        except ValueError:
            continue
        assert find_privileged_fields(payload) == []


def build(tmp_path, env=StubLabEnv):
    ids = iter(f"ep-{i}" for i in range(500))
    svc = EpisodeService(
        env,
        PublicRecordStore(tmp_path),
        id_factory=lambda: next(ids),
        environment_id="stub",
        code_version="t",
    )
    return TestClient(create_app(svc))


@pytest.mark.parametrize("seed", range(8))
def test_random_episodes_never_leak(tmp_path, seed):
    client = build(tmp_path)
    rng = random.Random(seed)
    kinds = ["MEASURE_STABILITY", "MEASURE_SEC", "MEASURE_SPR", "MEASURE_EPITOPE", "MEASURE_DEVELOPABILITY",
             "VALIDATE_ASSAY", "ORTHOGONAL_FUNCTION", "REDESIGN_STABILITY", "REDESIGN_SOLUBILITY", "REDESIGN_INTERFACE"]
    ids = []
    for _ in range(3):
        state = client.post("/episodes", json={"seed": rng.randrange(1000)}).json()
        ids.append(state["episode_id"])
        responses = [json.dumps(state)]
        for _ in range(rng.randrange(1, 8)):
            r = client.post(f"/episodes/{state['episode_id']}/actions", json={"action_type": rng.choice(kinds)})
            responses.append(r.text)
        responses.append(client.post(f"/episodes/{state['episode_id']}/actions", json={"action_type": rng.choice(["SELECT", "REJECT", "MODEL_INVALID", "ABSTAIN"])}).text)
        assert_clean(responses)
    assert_clean(walk_text(client, ids))


class LeakyCandidate(Candidate):
    """A subclass smuggling extra attributes; DTO conversion must drop them."""

    true_log_kd: float = 0.0


def test_subclassed_public_objects_cannot_smuggle_fields(tmp_path):
    class SmugglingEnv(StubLabEnv):
        def reset(self, seed=None):
            state = super().reset(seed)
            return state

        def step(self, action):
            result = super().step(action)
            return result

    client = build(tmp_path, SmugglingEnv)
    eid = client.post("/episodes", json={"seed": 1}).json()["episode_id"]
    client.post(f"/episodes/{eid}/actions", json={"action_type": "REDESIGN_INTERFACE"})
    assert_clean(walk_text(client, [eid]))
    candidate = LeakyCandidate.model_construct(candidate_id="c", generation=0, parent_candidate_id=None, true_log_kd=TRUTH_CANARY)
    assert "true_log_kd" not in dto.candidate_dto(candidate).model_dump_json()
    assert str(TRUTH_CANARY) not in dto.candidate_dto(candidate).model_dump_json()


def test_leak_guard_blocks_a_leaky_route(tmp_path):
    svc = EpisodeService(StubLabEnv, PublicRecordStore(tmp_path))
    app = create_app(svc)

    @app.get("/oops")
    def oops():
        return {"outer": [{"inner": {"_simulator_truth": {"log_kd": TRUTH_CANARY}}}]}

    @app.get("/oops-ok")
    def fine():
        return {"outer": [{"inner": {"log_kd": -7.0, "p_assay_invalid": 0.2}}]}

    client = TestClient(app)
    blocked = client.get("/oops")
    assert blocked.status_code == 500 and str(TRUTH_CANARY) not in blocked.text
    assert client.get("/oops-ok").status_code == 200


def test_guard_catches_every_nested_shape(tmp_path):
    svc = EpisodeService(StubLabEnv, PublicRecordStore(tmp_path))
    app = create_app(svc)
    payloads = {
        "list": [{"a": [{"b": {"particles": [1, 2]}}]}],
        "deep": {"a": {"b": {"c": {"d": {"hidden_state": 1}}}}},
        "validity": {"x": {"assay_validity": True}},
        "truthy": {"x": {"true_kd": 1}},
        "label": {"x": {"failure_labels": {}}},
    }
    for name, body in payloads.items():
        app.add_api_route(f"/leak-{name}", (lambda b=body: b), methods=["GET"])
    client = TestClient(app)
    for name in payloads:
        assert client.get(f"/leak-{name}").status_code == 500, name


def _models(root):
    seen, stack = set(), [root]
    while stack:
        model = stack.pop()
        if model in seen or not (isinstance(model, type) and issubclass(model, BaseModel)):
            continue
        seen.add(model)
        for field in model.model_fields.values():
            stack.extend(_inner_types(field.annotation))
    return seen


def _inner_types(annotation):
    out = [annotation]
    for arg in getattr(annotation, "__args__", ()) or ():
        out.extend(_inner_types(arg))
    return out


def test_dto_schemas_have_no_privileged_field_names_and_forbid_extras():
    roots = [dto.PublicStateDTO, dto.StepDTO, dto.ReplayDTO, dto.RecommendationDTO, dto.EventDTO]
    models = set().union(*(_models(r) for r in roots))
    assert len(models) >= 10
    for model in models:
        assert model.model_config.get("extra") == "forbid", model
        assert find_privileged_fields({name: 1 for name in model.model_fields}) == [], model


def test_belief_dto_rejects_particles_and_truth():
    for extra in ({"particles": [[0.1]]}, {"true_log_kd": -8.0}, {"_simulator_truth": {}}):
        with pytest.raises(ValueError):
            dto.belief_dto({**make_belief(), **extra})
    with pytest.raises(ValueError):
        validate_belief_payload({**make_belief(), "latent_samples": []})


def test_replay_from_disk_with_tampered_file_is_refused(tmp_path):
    client = build(tmp_path)
    eid = client.post("/episodes", json={"seed": 2}).json()["episode_id"]
    client.post(f"/episodes/{eid}/actions", json={"action_type": "ABSTAIN"})
    path = tmp_path / f"{eid}.jsonl"
    lines = path.read_text().splitlines()
    event = json.loads(lines[1])
    event["_simulator_truth"] = {"log_kd": TRUTH_CANARY}
    lines[1] = json.dumps(event)
    path.write_text("\n".join(lines) + "\n")
    fresh = TestClient(create_app(EpisodeService(StubLabEnv, PublicRecordStore(tmp_path))))
    r = fresh.get(f"/episodes/{eid}/replay")
    assert r.status_code == 500 and str(TRUTH_CANARY) not in r.text
    assert r.json() == {"detail": "stored episode failed validation"}


def test_request_cannot_inject_truth_via_action_body(tmp_path):
    client = build(tmp_path)
    eid = client.post("/episodes").json()["episode_id"]
    r = client.post(f"/episodes/{eid}/actions", json={"action_type": "ABSTAIN", "metadata": {"x": 1}})
    assert r.status_code == 422
    action = ScientificAction(action_type="ABSTAIN")
    assert "metadata" not in action.model_dump()
