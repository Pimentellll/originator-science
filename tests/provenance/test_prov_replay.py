"""D0b: recorder, JSONL storage, deterministic replay, determinism verification."""

import json
import subprocess
import sys
import textwrap

import pytest

from campaign_support import TRUTH_CANARY, StubLabEnv, TraceBuilder, confident, make_belief
from mirage.core import ActionType, ScientificAction
from mirage.provenance import (
    EpisodeRecorder,
    PolicyMetadata,
    ProvenanceError,
    PublicRecordStore,
    Replay,
    record_from_jsonl,
    record_to_jsonl,
    validate_record,
    verify_deterministic_source,
)

SCRIPT = [ActionType.MEASURE_SEC, ActionType.MEASURE_SPR, ActionType.REDESIGN_SOLUBILITY, ActionType.MEASURE_STABILITY, ActionType.SELECT]


def run_stub(seed: int, episode_id: str = "ep-stub"):
    env = StubLabEnv()
    state = env.reset(seed=seed)
    rec = EpisodeRecorder(
        episode_id=episode_id, seed=seed, initial_state=state, policy=PolicyMetadata(name="scripted"),
        environment_id="stub", code_version="test",
    )
    for kind in SCRIPT:
        before = env.agent_state()
        action = ScientificAction(action_type=kind, candidate_id=before.active_candidate.candidate_id)
        result = env.step(action)
        rec.record_step(state_before=before, action=action, result=result,
                        belief_before=make_belief(), belief_after=make_belief() if kind != ActionType.SELECT else make_belief())
    return rec.finish()


def test_recorder_builds_valid_record():
    record = run_stub(3)
    assert validate_record(record) == []
    assert record.terminal_decision.action_type == ActionType.SELECT
    redesign = record.events[2]
    assert redesign.child_candidate_id == "cand-0-r3"
    assert record.events[3].candidate_id == "cand-0-r3"


def test_recorder_rejects_steps_after_terminal():
    env = StubLabEnv()
    state = env.reset(seed=1)
    rec = EpisodeRecorder(episode_id="e", seed=1, initial_state=state, policy=PolicyMetadata(name="p"), environment_id="stub", code_version="t")
    action = ScientificAction(action_type=ActionType.ABSTAIN)
    result = env.step(action)
    rec.record_step(state_before=state, action=action, result=result)
    assert rec.finished
    with pytest.raises(ValueError):
        rec.record_step(state_before=result.state, action=action, result=result)


def test_same_seed_same_trace_different_seed_differs():
    assert run_stub(7).digest() == run_stub(7).digest()
    assert run_stub(7).digest() != run_stub(8).digest()


def test_verify_deterministic_source():
    record = run_stub(11)
    assert verify_deterministic_source(record, StubLabEnv) == []
    tampered = record.model_copy(update={"seed": 12})
    assert verify_deterministic_source(tampered, StubLabEnv)


def test_jsonl_roundtrip_exact():
    record = run_stub(5)
    text = record_to_jsonl(record)
    lines = text.strip().splitlines()
    assert len(lines) == len(record.events) + 2
    assert json.loads(lines[0])["kind"] == "header" and json.loads(lines[-1])["kind"] == "terminal"
    assert record_from_jsonl(text) == record


def test_jsonl_never_contains_truth(tmp_path):
    record = run_stub(5)
    path = PublicRecordStore(tmp_path).save(record)
    raw = path.read_text()
    assert str(TRUTH_CANARY) not in raw and "_simulator_truth" not in raw and "aggregated" not in raw


def test_store_roundtrip_listing_and_safety(tmp_path):
    store = PublicRecordStore(tmp_path / "public")
    record = run_stub(5, "ep-a")
    store.save(record)
    assert store.list_ids() == ["ep-a"] and store.exists("ep-a")
    assert store.load("ep-a") == record
    for bad in ("../x", "a/b", ".hidden", ""):
        with pytest.raises(ValueError):
            store.load(bad)
    with pytest.raises(FileNotFoundError):
        store.load("missing")


def test_store_refuses_invalid_record(tmp_path):
    record = run_stub(5).model_copy(update={"terminal_decision": None})
    with pytest.raises(ProvenanceError):
        PublicRecordStore(tmp_path).save(record)


def test_replay_frames_and_lineage():
    record = run_stub(5)
    replay = Replay(record)
    assert len(replay) == len(record.events)
    frame = replay.at(2)
    assert frame.active_candidate_id == "cand-0-r3"
    assert [c.candidate_id for c in frame.candidates] == ["cand-0", "cand-0-r3"]
    assert frame.candidates[1].generation == 1 and frame.candidates[1].parent_candidate_id == "cand-0"
    assert replay.at(len(replay) - 1).terminal and not replay.at(0).terminal
    assert [f.resources for f in replay] == [e.resources_after for e in record.events]


def test_replay_is_pure_function_of_record():
    record = run_stub(5)
    assert list(Replay(record)) == list(Replay(record_from_jsonl(record_to_jsonl(record))))


def test_replay_refuses_invalid_record():
    record = run_stub(5).model_copy(update={"terminal_decision": None})
    with pytest.raises(ProvenanceError):
        Replay(record)


def test_replay_needs_no_model_policy_or_environment(tmp_path):
    """G11: replaying a stored trace must not import or call env/PPO/LLM/belief engines."""
    path = PublicRecordStore(tmp_path).save(run_stub(5))
    program = textwrap.dedent(
        f"""
        import sys
        for name in ("anthropic", "torch", "stable_baselines3", "sb3_contrib", "gymnasium",
                     "mirage.belief", "mirage.policies", "mirage.lab", "mirage.agents"):
            sys.modules[name] = None  # any import of these now raises ImportError
        import random
        random.seed = lambda *a, **k: (_ for _ in ()).throw(AssertionError("RNG touched"))
        from mirage.provenance import PublicRecordStore, Replay
        record = PublicRecordStore({str(tmp_path)!r}).load("ep-stub")
        frames = list(Replay(record))
        assert len(frames) == {len(SCRIPT)}
        print("ok")
        """
    )
    out = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stderr
