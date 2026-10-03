import hashlib
import json
import math

import pytest
from pydantic import ValidationError

from mirage.agents.base import Agent, LabSession
from mirage.lab import tools
from mirage.lab.tools import (
    AgentState,
    Diagnosis,
    MeasurementRequest,
    MeasurementResult,
    Observation,
    ToolResponse,
)


def test_limit_constants_match_design_5_8() -> None:
    assert (tools.MAX_TIME_H, tools.MAX_DILUTION, tools.MAX_REPLICATES) == (18, 100.0, 3)
    assert (tools.BUDGET_UNITS, tools.MAX_TURNS) == (6, 12)


def test_request_defaults_scripted_api() -> None:
    req = MeasurementRequest(time_h=18)
    assert (req.dilution_factor, req.replicates) == (1.0, 1)


@pytest.mark.parametrize(
    "args",
    [
        {"time_h": -1},
        {"time_h": 19},
        {"time_h": 2.5},
        {"time_h": "18"},
        {"time_h": True},
        {"time_h": 18, "dilution_factor": 0.5},
        {"time_h": 18, "dilution_factor": 0},
        {"time_h": 18, "dilution_factor": 101},
        {"time_h": 18, "dilution_factor": math.nan},
        {"time_h": 18, "dilution_factor": "10"},
        {"time_h": 18, "replicates": 0},
        {"time_h": 18, "replicates": 4},
        {"time_h": 18, "extra": 1},
        {},
    ],
)
def test_request_rejects_invalid_arguments(args: dict) -> None:
    with pytest.raises(ValidationError):
        MeasurementRequest(**args)


@pytest.mark.parametrize("d", [1, 1.0, 10, 100.0])
def test_request_accepts_valid_dilution(d: float) -> None:
    assert MeasurementRequest(time_h=0, dilution_factor=d, replicates=3).dilution_factor == d


def test_diagnosis_validation() -> None:
    Diagnosis(diagnosis="GROWTH_CONTINUED", p_growth_continued=1.0, rationale="")
    for bad in (
        {"diagnosis": "MEASUREMENT_ARTIFACT", "p_growth_continued": 0.5, "rationale": ""},
        {"diagnosis": "GROWTH_STOPPED", "p_growth_continued": 1.5, "rationale": ""},
        {"diagnosis": "GROWTH_STOPPED", "p_growth_continued": 0.5, "rationale": "x" * 4001},
        {"diagnosis": "GROWTH_STOPPED", "p_growth_continued": 0.5, "rationale": "",
         "late_biomass_estimate_od": -1.0},
    ):
        with pytest.raises(ValidationError):
            Diagnosis(**bad)
    with pytest.raises(ValidationError):
        AgentState(notes="x" * 2001, p_growth_continued=0.5)


def test_models_are_frozen() -> None:
    req = MeasurementRequest(time_h=3)
    with pytest.raises(ValidationError):
        req.time_h = 4  # type: ignore[misc]


def _passive(i: int, y: float) -> MeasurementResult:
    return MeasurementResult(
        source="passive", request_index=None, time_h=i, dilution_factor=1.0,
        readings=[y], mean_reading=y, cost_units=0, budget_remaining=6,
    )


def test_render_observation_layout_design_10() -> None:
    obs = Observation(
        passive_readings=[_passive(i, 0.01 * (i + 1)) for i in range(19)],
        budget_total=6,
        budget_remaining=6,
    )
    text = tools.render_observation(obs)
    data = json.loads(text)
    assert set(data) == {"budget", "experiment", "limits", "passive_readings"}
    assert data["budget"] == {
        "cost": "1 unit per replicate reading", "remaining_units": 6, "total_units": 6,
    }
    assert set(data["experiment"]) == {"assay", "culture", "retained_aliquots_h"}
    assert data["experiment"]["retained_aliquots_h"] == list(range(19))
    assert data["limits"] == {
        "dilution_factor": "1 to 100", "max_turns": 12,
        "replicates": "1 to 3", "time_h": "integer 0 to 18",
    }
    assert data["passive_readings"][3] == {"dilution_factor": 1.0, "reading": 0.04, "time_h": 3}
    assert text == json.dumps(data, sort_keys=True, ensure_ascii=False)


def test_render_measurement_layout_design_10() -> None:
    res = MeasurementResult(
        source="agent", request_index=0, time_h=18, dilution_factor=10.0,
        readings=[0.4012, 0.3987, 0.4031], mean_reading=0.401, cost_units=3,
        budget_remaining=3,
    )
    assert tools.render_measurement(res) == {
        "budget_remaining": 3, "dilution_factor": 10.0, "mean_reading": 0.401,
        "readings": [0.4012, 0.3987, 0.4031], "time_h": 18,
    }


def test_tool_definitions_shape_design_9_2() -> None:
    assert tools.TOOL_NAMES == ("measure_od", "declare_state", "submit_diagnosis")
    for d in tools.TOOL_DEFINITIONS:
        assert d["strict"] is True
        schema = d["input_schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
    assert tools.TOOL_DEFINITIONS[1]["description"].startswith("Optional.")


def test_prompt_sha256_is_stable_hex() -> None:
    h = tools.prompt_sha256()
    assert h == tools.prompt_sha256() and len(h) == 64
    int(h, 16)


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def observation(self) -> Observation:
        return Observation(passive_readings=[], budget_total=6, budget_remaining=6)

    def call(self, tool: str, args: dict) -> ToolResponse:
        self.calls.append(tool)
        return ToolResponse(ok=True, result={}, error=None)

    @property
    def finished(self) -> bool:
        return bool(self.calls)


class _OneShot:
    def run(self, session: LabSession) -> None:
        session.call("submit_diagnosis", {})


def test_protocols_are_structural() -> None:
    session = _FakeSession()
    agent: Agent = _OneShot()
    agent.run(session)
    assert session.finished and session.calls == ["submit_diagnosis"]


# ---- review fixes (fix/lab-validation) ------------------------------------------------------

NONFINITE = [float("nan"), float("inf"), float("-inf")]


def _result(**kw) -> dict:
    base = dict(source="agent", request_index=0, time_h=18, dilution_factor=10.0,
                readings=[0.4012, -0.0021], mean_reading=0.1996, cost_units=2, budget_remaining=4)
    return {**base, **kw}


@pytest.mark.parametrize("bad", NONFINITE)
@pytest.mark.parametrize("field", ["readings", "mean_reading", "dilution_factor"])
def test_measurement_result_rejects_nonfinite(field, bad) -> None:
    value = [0.1, bad] if field == "readings" else bad
    with pytest.raises(ValidationError):
        MeasurementResult(**_result(**{field: value}))


@pytest.mark.parametrize("bad", NONFINITE)
def test_diagnosis_rejects_nonfinite_estimate(bad) -> None:
    with pytest.raises(ValidationError):
        Diagnosis(diagnosis="GROWTH_STOPPED", p_growth_continued=0.5,
                  late_biomass_estimate_od=bad, rationale="r")


def test_negative_blank_subtracted_readings_are_valid_and_render_as_json() -> None:
    res = MeasurementResult(**_result(readings=[-0.0031, 0.0004], mean_reading=-0.0014))
    payload = tools.render_measurement(res)
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload
    obs = Observation(passive_readings=[_passive(i, -0.0029 if i == 0 else 0.01) for i in range(19)],
                      budget_total=6, budget_remaining=6)
    data = json.loads(tools.render_observation(obs))
    assert data["passive_readings"][0]["reading"] == -0.0029


def test_rendering_rounds_to_four_decimals_both_signs() -> None:
    res = MeasurementResult(**_result(readings=[0.123449, -0.004561, 0.98765], mean_reading=-0.004561))
    out = tools.render_measurement(res)
    assert out["readings"] == [0.1234, -0.0046, 0.9877] and out["mean_reading"] == -0.0046
    obs = Observation(passive_readings=[_passive(i, 0.123456 if i else -0.000051) for i in range(19)],
                      budget_total=6, budget_remaining=6)
    data = json.loads(tools.render_observation(obs))
    assert data["passive_readings"][1]["reading"] == 0.1235
    assert data["passive_readings"][0]["reading"] == -0.0001


@pytest.mark.parametrize("model", [AgentState, Diagnosis])
def test_probability_bounds(model) -> None:
    extra = {"notes": "n"} if model is AgentState else {
        "diagnosis": "GROWTH_STOPPED", "late_biomass_estimate_od": None, "rationale": "r"}
    for p in (0.0, 0.5, 1.0):
        assert model(p_growth_continued=p, **extra).p_growth_continued == p
    for p in (-1e-9, 1 + 1e-9, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            model(p_growth_continued=p, **extra)


@pytest.mark.parametrize("value", [True, False, 2.0, "2", None, [2]])
def test_replicates_strict_type(value) -> None:
    with pytest.raises(ValidationError):
        MeasurementRequest(time_h=18, replicates=value)


@pytest.mark.parametrize("value", [True, 18.0, "18", None])
def test_time_strict_type(value) -> None:
    with pytest.raises(ValidationError):
        MeasurementRequest(time_h=value)


def test_tool_property_types_enums_and_wording_exact() -> None:
    props = {d["name"]: d["input_schema"]["properties"] for d in tools.TOOL_DEFINITIONS}
    types_ = {name: {k: v["type"] for k, v in p.items()} for name, p in props.items()}
    assert types_ == {
        "measure_od": {"time_h": "integer", "dilution_factor": "number", "replicates": "integer"},
        "declare_state": {"notes": "string", "p_growth_continued": "number"},
        "submit_diagnosis": {"diagnosis": "string", "p_growth_continued": "number",
                             "late_biomass_estimate_od": ["number", "null"], "rationale": "string"},
    }
    assert props["submit_diagnosis"]["diagnosis"]["enum"] == ["GROWTH_STOPPED", "GROWTH_CONTINUED"]
    assert sum("enum" in v for p in props.values() for v in p.values()) == 1
    assert [d["required"] for d in (t["input_schema"] for t in tools.TOOL_DEFINITIONS)] == [
        ["time_h", "dilution_factor", "replicates"], ["notes", "p_growth_continued"],
        ["diagnosis", "p_growth_continued", "late_biomass_estimate_od", "rationale"]]
    assert props["measure_od"]["replicates"]["description"] == "Number of independent replicate reads: 1, 2 or 3."
    assert tools.TOOL_DEFINITIONS[2]["description"] == (
        "Submit your conclusion. This ends the experiment; no further measurements are possible.")
    assert tools.SYSTEM_PROMPT.startswith(
        "You are an autonomous scientist working in a virtual microbiology laboratory.\n\n")
    assert tools.SYSTEM_PROMPT.endswith("Finish by calling submit_diagnosis. You have\nat most 12 turns.")


PROMPT_V1_SHA256 = "6df242e5a8c22cfa7f2dfdde25ec1038262f5d89d1bc4305456383217d8db12b"


def test_prompt_v1_digest_frozen_and_independently_computed() -> None:
    canonical = json.dumps({"system": tools.SYSTEM_PROMPT, "tools": tools.TOOL_DEFINITIONS},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == PROMPT_V1_SHA256
    assert tools.prompt_sha256() == PROMPT_V1_SHA256 and tools.PROMPT_VERSION == "prompt-v1"
