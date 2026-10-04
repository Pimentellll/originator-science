"""Registered system-prompt variants for the exploratory prompt ablation."""

from __future__ import annotations

import hashlib
import json

from mirage.lab.tools import TOOL_DEFINITIONS

PROMPTS = {
    "prompt-v2-noceiling": """\
You are an autonomous scientist working in a virtual microbiology laboratory.

A bacterial batch culture was inoculated at t = 0 h and incubated for 18 h. Its
optical density at 600 nm (OD600) was read every hour on a plate reader, and an
aliquot of the culture was withdrawn and retained every hour. The hourly readings
are provided in the first message.

Your task is to decide whether, over the final hours of the experiment, the
culture's biomass is at the level the readings indicate, or higher than
the readings indicate, and to support your conclusion with evidence.

You may request additional measurements with measure_od; each replicate reading
costs 1 unit from a budget of 6 units. Finish by calling submit_diagnosis. You have
at most 12 turns.""",
    "prompt-v2-minimal": """\
A bacterial batch culture was incubated for 18 h and its OD600 was read every hour. The
hourly readings are provided in the first message.

Decide whether, over the final hours of the experiment, the culture's biomass is at the
level the readings indicate, or higher than the readings indicate.

Tools: measure_od (each replicate reading costs 1 unit from a budget of 6 units),
declare_state (optional, free) and submit_diagnosis (ends the experiment). You have at
most 12 turns.""",
}


def variant_sha256(system: str) -> str:
    """Hash a variant system prompt with the frozen tool definitions."""
    payload = json.dumps(
        {"system": system, "tools": TOOL_DEFINITIONS},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
