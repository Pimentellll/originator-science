"""Prompt variants for the exploratory cue-ablation experiment (REGISTRATION.md §3).

Nothing here edits frozen source: each variant is built from a deep copy of the frozen
``mirage.lab.tools`` prompt-v2 objects, with named string substitutions only. Tool names and
``input_schema`` structure (parameter names, types, enums, required, strict,
additionalProperties) are never changed, so the output format and the evaluator are unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from mirage.lab import tools as frozen
from mirage.lab.tools import Observation

ASSAY_V2 = "OD600 plate reader; blank-subtracted readings of undiluted culture"


@dataclass(frozen=True)
class PromptVariant:
    version: str
    system: str
    tools: list[dict[str, Any]]
    assay: str = ASSAY_V2  # observation ``experiment.assay`` string
    notes: str = ""
    substitutions: tuple[tuple[str, str, str], ...] = field(default=())  # (where, old, new)

    def sha256(self) -> str:
        """Same formula as ``mirage.lab.tools.prompt_sha256``; the assay string is added only
        when it differs from prompt-v2, so the identity variant hashes to the frozen value."""
        payload: dict[str, Any] = {"system": self.system, "tools": self.tools}
        if self.assay != ASSAY_V2:
            payload["assay"] = self.assay
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def render_observation(self) -> Callable[[Observation], str]:
        """Frozen renderer, with only ``experiment.assay`` replaced (if it differs)."""
        if self.assay == ASSAY_V2:
            return frozen.render_observation

        def render(obs: Observation) -> str:
            payload = json.loads(frozen.render_observation(obs))
            assert payload["experiment"]["assay"] == ASSAY_V2
            payload["experiment"]["assay"] = self.assay
            # Same serialisation as the frozen renderer (sort_keys, no NaN); values were
            # already rounded to 4 dp there, and a JSON round trip preserves them.
            return json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)

        return render


def _sub(text: str, old: str, new: str, count: int = 1) -> str:
    """Replace exactly ``count`` occurrences of ``old``; fail loudly otherwise."""
    found = text.count(old)
    if found != count:
        raise ValueError(f"expected {count} occurrence(s) of {old!r}, found {found}")
    return text.replace(old, new)


def _tool(tools: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(t for t in tools if t["name"] == name)


# --- prompt-v2 (identity, used only by tests to prove the subclass is transparent) ---------

PROMPT_V2 = PromptVariant(
    version=frozen.PROMPT_VERSION,
    system=frozen.SYSTEM_PROMPT,
    tools=copy.deepcopy(frozen.TOOL_DEFINITIONS),
)

# --- prompt-v2-noceiling: system prompt only (cues S3, S4) ---------------------------------

_NOCEILING_SUBS = (
    ("system", "at the level the undiluted readings indicate, or higher than\nthe undiluted readings indicate",
     "at the level the readings indicate, or higher than\nthe readings indicate"),
)


def _build_noceiling() -> PromptVariant:
    system = frozen.SYSTEM_PROMPT
    for _, old, new in _NOCEILING_SUBS:
        system = _sub(system, old, new)
    return PromptVariant(
        version="prompt-v2-noceiling",
        system=system,
        tools=copy.deepcopy(frozen.TOOL_DEFINITIONS),
        notes="System prompt: 'undiluted' removed twice (S3, S4). Tools and observation identical.",
        substitutions=_NOCEILING_SUBS,
    )


# --- prompt-v2-minimal: task + tool list; tool descriptions and assay neutralised ----------

MINIMAL_SYSTEM = """\
You are working in a virtual microbiology laboratory.

A bacterial batch culture was incubated for 18 h and its OD600 was read every hour.
The readings are in the first message.

Task: decide whether, over the final hours, the culture's biomass is at the level
the readings indicate (BIOMASS_AS_READ) or higher (BIOMASS_ABOVE_READING).

Tools: measure_od (1 budget unit per replicate; 6 units in total), declare_state
(optional, free), submit_diagnosis (ends the experiment). At most 12 turns."""

MINIMAL_ASSAY = "OD600; blank-subtracted readings of culture"

# (json path, old, new). Paths: tool/name[/property]/description.
_MINIMAL_TOOL_SUBS = (
    ("measure_od/description",
     "Analyse a retained aliquot of the culture on the OD600 plate reader. Aliquots were "
     "withdrawn and retained every hour from 0 to 18 h; withdrawing them did not affect the "
     "culture. The aliquot from the requested hour is diluted in sterile medium by the given "
     "factor (1 = undiluted; 10 = 1 part aliquot + 9 parts medium) and read. Each replicate is "
     "an independent dilution and read, and costs 1 budget unit. Returns the blank-subtracted "
     "OD600 reading of each replicate exactly as read; no correction is applied.",
     "Analyse a retained aliquot of the culture on the OD600 plate reader. Aliquots were "
     "withdrawn and retained every hour from 0 to 18 h; withdrawing them did not affect the "
     "culture. The aliquot from the requested hour is read after diluting it in sterile medium "
     "by the given factor. Each replicate "
     "is an independent dilution and read, and costs 1 budget unit. Returns the OD600 reading "
     "of the diluted sample for each replicate."),
    ("measure_od/dilution_factor/description",
     "Total dilution factor applied before reading: from 1 (undiluted) to 100.",
     "Total dilution factor applied before reading: from 1 to 100."),
    ("declare_state/description",
     "Optional. Record your current notes and your current probability that, over the final "
     "hours, the culture's biomass is higher than the undiluted readings indicate. Free of "
     "charge; never required.",
     "Optional. Record your current notes and your current probability that, over the final "
     "hours, the culture's biomass is higher than the readings indicate. Free of charge; "
     "never required."),
    ("declare_state/p_biomass_above_reading/description",
     "Probability from 0 to 1 that, over the final hours, biomass is higher than the undiluted "
     "readings indicate.",
     "Probability from 0 to 1 that, over the final hours, biomass is higher than the readings "
     "indicate."),
    ("submit_diagnosis/diagnosis/description",
     "Whether, over the final hours, the culture's biomass is at the level the undiluted "
     "readings indicate (BIOMASS_AS_READ) or higher than they indicate (BIOMASS_ABOVE_READING).",
     "Whether, over the final hours, the culture's biomass is at the level the readings "
     "indicate (BIOMASS_AS_READ) or higher than they indicate (BIOMASS_ABOVE_READING)."),
    ("submit_diagnosis/p_biomass_above_reading/description",
     "Probability from 0 to 1 that, over the final hours, biomass is higher than the undiluted "
     "readings indicate.",
     "Probability from 0 to 1 that, over the final hours, biomass is higher than the readings "
     "indicate."),
    ("submit_diagnosis/late_biomass_estimate_od/description",
     "Your estimate of the culture's OD600 at 18 h, expressed as the reading an undiluted "
     "sample would give if the reader responded proportionally; null if you have no estimate.",
     "Your estimate of the culture's OD600 at 18 h; null if you have no estimate."),
    ("submit_diagnosis/rationale/description",
     "Evidence-based justification.",
     "Justification for the diagnosis."),
)


def _node(tools: list[dict[str, Any]], path: str) -> dict[str, Any]:
    parts = path.split("/")
    tool = _tool(tools, parts[0])
    if len(parts) == 2:
        return tool
    return tool["input_schema"]["properties"][parts[1]]


def _build_minimal() -> PromptVariant:
    tools = copy.deepcopy(frozen.TOOL_DEFINITIONS)
    for path, old, new in _MINIMAL_TOOL_SUBS:
        node = _node(tools, path)
        if node["description"] != old:
            raise ValueError(f"{path}: frozen description changed; refusing to build variant")
        node["description"] = new
    subs = (("system", frozen.SYSTEM_PROMPT, MINIMAL_SYSTEM), *_MINIMAL_TOOL_SUBS,
            ("observation/experiment.assay", ASSAY_V2, MINIMAL_ASSAY))
    return PromptVariant(
        version="prompt-v2-minimal",
        system=MINIMAL_SYSTEM,
        tools=tools,
        assay=MINIMAL_ASSAY,
        notes="Task statement + tool list; tool descriptions and observation assay neutralised.",
        substitutions=subs,
    )


PROMPT_V2_NOCEILING = _build_noceiling()
PROMPT_V2_MINIMAL = _build_minimal()

VARIANTS: dict[str, PromptVariant] = {
    v.version: v for v in (PROMPT_V2, PROMPT_V2_NOCEILING, PROMPT_V2_MINIMAL)
}


def schema_skeleton(tools: list[dict[str, Any]]) -> Any:
    """Tool definitions with every ``description`` removed: must be identical across variants."""

    def strip(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: strip(v) for k, v in obj.items() if k != "description"}
        if isinstance(obj, list):
            return [strip(v) for v in obj]
        return obj

    return strip(tools)
