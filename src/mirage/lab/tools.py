"""VISIBLE agent-facing interface: schemas, tool definitions, prompt, limits (DESIGN §§9-13).

Frozen once merged. Must not import any hidden module (DESIGN §12, T-012).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_TIME_H = 18
MAX_DILUTION = 100.0
MAX_REPLICATES = 3
BUDGET_UNITS = 6
MAX_TURNS = 12

PROMPT_VERSION = "prompt-v1"

GrowthLabel = Literal["GROWTH_STOPPED", "GROWTH_CONTINUED"]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MeasurementRequest(Frozen):
    # strict: "18" and 2.5 must be rejected, not coerced (T-020).
    time_h: int = Field(ge=0, le=MAX_TIME_H, strict=True)
    dilution_factor: float = Field(default=1.0, ge=1.0, le=MAX_DILUTION, strict=True)
    replicates: int = Field(default=1, ge=1, le=MAX_REPLICATES, strict=True)


class MeasurementResult(Frozen):
    source: Literal["passive", "agent"]
    request_index: int | None
    time_h: int
    dilution_factor: float
    readings: list[float]
    mean_reading: float
    cost_units: int
    budget_remaining: int


class AgentState(Frozen):
    notes: str = Field(max_length=2000)
    p_growth_continued: float = Field(ge=0, le=1)


class Diagnosis(Frozen):
    diagnosis: GrowthLabel
    p_growth_continued: float = Field(ge=0, le=1)
    late_biomass_estimate_od: float | None = Field(default=None, ge=0)
    rationale: str = Field(max_length=4000)


class Observation(Frozen):
    passive_readings: list[MeasurementResult]
    budget_total: int
    budget_remaining: int


class ToolResponse(Frozen):
    """What ``LabSession.call`` returns. ``result`` is the §10 tool_result payload."""

    ok: bool
    result: dict[str, Any] | None
    error: str | None


SYSTEM_PROMPT = """\
You are an autonomous scientist working in a virtual microbiology laboratory.

A bacterial batch culture was inoculated at t = 0 h and incubated for 18 h. Its
optical density at 600 nm (OD600) was read every hour on a plate reader, and an
aliquot of the culture was withdrawn and retained every hour. The hourly readings
are provided in the first message.

Your task is to decide whether the culture's biomass stopped increasing, or
continued to increase, over the final hours of the experiment, and to support your
conclusion with evidence.

You may request additional measurements with measure_od; each replicate reading
costs 1 unit from a budget of 6 units. Finish by calling submit_diagnosis. You have
at most 12 turns."""

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "measure_od",
        "description": "Analyse a retained aliquot of the culture on the OD600 plate reader. Aliquots were withdrawn and retained every hour from 0 to 18 h; withdrawing them did not affect the culture. The aliquot from the requested hour is diluted in sterile medium by the given factor (1 = undiluted; 10 = 1 part aliquot + 9 parts medium) and read. Each replicate is an independent dilution and read, and costs 1 budget unit. Returns the blank-subtracted OD600 reading of each replicate exactly as read; no correction is applied.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "time_h": {"type": "integer", "description": "Hour at which the aliquot was withdrawn: an integer from 0 to 18."},
                "dilution_factor": {"type": "number", "description": "Total dilution factor applied before reading: from 1 (undiluted) to 100."},
                "replicates": {"type": "integer", "description": "Number of independent replicate reads: 1, 2 or 3."},
            },
            "required": ["time_h", "dilution_factor", "replicates"],
            "additionalProperties": False,
        },
    },
    {
        "name": "declare_state",
        "description": "Optional. Record your current notes and your current probability that the culture's biomass continued to increase over the final hours. Free of charge; never required.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "notes": {"type": "string", "description": "Free-text notes on your current thinking."},
                "p_growth_continued": {"type": "number", "description": "Probability from 0 to 1."},
            },
            "required": ["notes", "p_growth_continued"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_diagnosis",
        "description": "Submit your conclusion. This ends the experiment; no further measurements are possible.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "diagnosis": {"type": "string", "enum": ["GROWTH_STOPPED", "GROWTH_CONTINUED"], "description": "Whether the culture's biomass stopped increasing or continued to increase over the final hours of the experiment."},
                "p_growth_continued": {"type": "number", "description": "Probability from 0 to 1 that biomass continued to increase."},
                "late_biomass_estimate_od": {"type": ["number", "null"], "description": "Your estimate of the culture's OD600 at 18 h, expressed as the reading an undiluted sample would give if the reader responded proportionally; null if you have no estimate."},
                "rationale": {"type": "string", "description": "Evidence-based justification."},
            },
            "required": ["diagnosis", "p_growth_continued", "late_biomass_estimate_od", "rationale"],
            "additionalProperties": False,
        },
    },
]

TOOL_NAMES = tuple(d["name"] for d in TOOL_DEFINITIONS)


def prompt_sha256() -> str:
    """SHA-256 of the system prompt plus tool definitions (recorded as ``prompt_sha256``)."""
    payload = json.dumps(
        {"system": SYSTEM_PROMPT, "tools": TOOL_DEFINITIONS},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_observation(obs: Observation) -> str:
    """Serialise the initial observation to the DESIGN §10 JSON layout (sorted keys, 4 dp)."""
    payload = {
        "budget": {
            "cost": "1 unit per replicate reading",
            "remaining_units": obs.budget_remaining,
            "total_units": obs.budget_total,
        },
        "experiment": {
            "assay": "OD600 plate reader; blank-subtracted readings of undiluted culture",
            "culture": "bacterial batch culture inoculated at t = 0 h, incubated 18 h",
            "retained_aliquots_h": list(range(MAX_TIME_H + 1)),
        },
        "limits": {
            "dilution_factor": f"1 to {MAX_DILUTION:g}",
            "max_turns": MAX_TURNS,
            "replicates": f"1 to {MAX_REPLICATES}",
            "time_h": f"integer 0 to {MAX_TIME_H}",
        },
        "passive_readings": [
            {
                "dilution_factor": m.dilution_factor,
                "reading": round(m.mean_reading, 4),
                "time_h": m.time_h,
            }
            for m in obs.passive_readings
        ],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def render_measurement(result: MeasurementResult) -> dict[str, Any]:
    """The DESIGN §10 ``measure_od`` tool_result payload."""
    return {
        "budget_remaining": result.budget_remaining,
        "dilution_factor": result.dilution_factor,
        "mean_reading": round(result.mean_reading, 4),
        "readings": [round(y, 4) for y in result.readings],
        "time_h": result.time_h,
    }
