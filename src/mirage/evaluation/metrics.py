"""HIDDEN: episode record schemas (DESIGN §13 RECORDS).

Audit and scoring (DEV-008) are added here later. Must not import ``anthropic`` (§12).
"""

from __future__ import annotations

from typing import Any, Literal

from mirage.config import EpisodeConfig, Frozen
from mirage.lab.tools import Diagnosis, MeasurementResult

SCHEMA_VERSION = "episode-result-v1"

EpisodeStatus = Literal["DIAGNOSED", "NO_DIAGNOSIS", "API_FAILURE", "REFUSED"]


class EventRecord(Frozen):
    index: int
    turn: int
    tool: str
    arguments: dict[str, Any]
    ok: bool
    result: dict[str, Any] | None
    error: str | None


class MeasurementAudit(Frozen):
    event_index: int
    request_index: int
    latent_biomass_odeq: float
    presented_biomass_odeq: float
    noise_free_reading: float
    is_late: bool
    is_diluted: bool
    in_diagnostic_set: bool
    before_diagnosis: bool
    diagnostic_control: bool
    in_useful_region: bool
    reconstruction_adequate: bool


class EpisodeScores(Frozen):
    correct: bool
    diagnostic_control: bool
    justified: bool
    reconstruction_adequate: bool
    cost_units: int
    measure_calls_before_diagnosis: int
    brier: float | None
    m5_diagnosticity: float | None


class AgentInfo(Frozen):
    name: str
    kind: Literal["llm", "scripted"]
    model: str | None
    effort: str | None
    prompt_version: str | None
    prompt_sha256: str | None
    sdk_version: str | None


class DiagnosticActionSet(Frozen):
    scenario_sha256: str
    late_window_h: tuple[int, int]
    d_min: float
    d_max: float
    auroc_threshold: float
    evaluated_replicates: int


class EpisodeResult(Frozen):
    schema_version: Literal["episode-result-v1"]
    episode: EpisodeConfig
    agent: AgentInfo
    passive: list[MeasurementResult]
    events: list[EventRecord]
    diagnosis: Diagnosis | None
    status: EpisodeStatus
    audit: list[MeasurementAudit]
    scores: EpisodeScores
    llm_transcript: list[dict[str, Any]] | None
    versions: dict[str, str]
    run_meta: dict[str, Any]
