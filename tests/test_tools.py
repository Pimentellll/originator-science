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
