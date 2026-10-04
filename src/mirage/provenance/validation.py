"""Semantic checks on stored public episodes (PROVENANCE_AND_REPLAY.md, required checks)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mirage.core import ActionType, ResourceState, ScientificAction, ScientificEnvironment
from mirage.provenance.compat import (
    ACTION_MEASUREMENTS,
    MEASUREMENT_ACTIONS,
    REDESIGN_ACTIONS,
    TERMINAL_ACTIONS,
    measurements_of,
)
from mirage.provenance.events import EpisodeRecord
from mirage.provenance.leakage import find_privileged_fields

_EPS = 1e-9


@dataclass(frozen=True)
class ProvenanceIssue:
    code: str
    step: int | None
    message: str

    def __str__(self) -> str:
        where = "record" if self.step is None else f"step {self.step}"
        return f"[{self.code}] {where}: {self.message}"


class ProvenanceError(ValueError):
    def __init__(self, issues: list[ProvenanceIssue]) -> None:
        self.issues = issues
        super().__init__("; ".join(str(i) for i in issues))


def _consumed(before: ResourceState, after: ResourceState) -> bool:
    return (
        after.budget_remaining < before.budget_remaining - _EPS
        or after.sample_remaining < before.sample_remaining - _EPS
        or after.simulated_time > before.simulated_time + _EPS
    )


def _same(a: ResourceState, b: ResourceState) -> bool:
    return a.model_dump() == b.model_dump()


def validate_record(record: EpisodeRecord) -> list[ProvenanceIssue]:
    """Contiguous steps, schema validity, resource accounting, lineage, public-only."""
    issues: list[ProvenanceIssue] = []

    def add(code: str, step: int | None, message: str) -> None:
        issues.append(ProvenanceIssue(code, step, message))

    for path in find_privileged_fields(record.model_dump(mode="json")):
        add("privileged_field", None, f"privileged-looking field {path}")

    known = {c.candidate_id for c in record.initial_state.candidates}
    known.add(record.initial_state.active_candidate.candidate_id)
    expected_resources = record.initial_state.resources
    terminal_seen = False

    for index, event in enumerate(record.events):
        step = event.step
        kind = event.action.action_type
        if step != index:
            add("non_contiguous_step", step, f"expected step {index}")
        if terminal_seen:
            add("event_after_terminal", step, "no events may follow a terminal decision")
        if event.candidate_id not in known:
            add("unknown_candidate", step, f"candidate {event.candidate_id!r} is not in lineage")
        if event.action.candidate_id not in (None, event.candidate_id):
            add("candidate_mismatch", step, "action and event candidate differ")
        if not _same(event.resources_before, expected_resources):
            add("resource_discontinuity", step, "resources_before != previous resources_after")
        before, after = event.resources_before, event.resources_after
        if after.budget_remaining > before.budget_remaining + _EPS:
            add("resource_increase", step, "budget increased")
        if after.sample_remaining > before.sample_remaining + _EPS:
            add("resource_increase", step, "sample increased")
        if after.simulated_time < before.simulated_time - _EPS:
            add("time_reversal", step, "simulated time decreased")
        if after.spr_instrument_health > before.spr_instrument_health + _EPS:
            add("health_increase", step, "SPR health increased")

        if kind in MEASUREMENT_ACTIONS:
            if event.observation is None:
                # Public invalid-action outcome: legal only if nothing was charged.
                if not _same(before, after):
                    add("missing_observation", step, "measurement charged resources but has no result")
            else:
                if not _consumed(before, after):
                    add("uncharged_action", step, "measurement consumed no resource")
                names = set(measurements_of(event.observation))
                allowed = set(ACTION_MEASUREMENTS[kind])
                if not names or not names <= allowed:
                    add("measurement_schema", step, f"{kind.value} measurements {sorted(names)} not in {sorted(allowed)}")
        elif kind in REDESIGN_ACTIONS:
            if event.observation is not None:
                add("redesign_observation", step, "redesign returns no assay result")
            if not _consumed(before, after):
                add("uncharged_action", step, "redesign consumed no resource")
            child = event.child_candidate_id
            if child in known:
                add("duplicate_candidate", step, f"child {child!r} already exists")
            elif child is not None:
                known.add(child)
        elif kind in TERMINAL_ACTIONS:
            terminal_seen = True
            if event.observation is not None:
                add("terminal_observation", step, "terminal decisions return no observation")
            if not _same(before, after):
                add("terminal_resources", step, "terminal decision changed resources")
        expected_resources = event.resources_after

    last = record.events[-1] if record.events else None
    if record.terminal_decision is None:
        if terminal_seen:
            add("terminal_not_recorded", None, "terminal event present but terminal_decision unset")
    else:
        if last is None or last.action.action_type not in TERMINAL_ACTIONS:
            add("terminal_mismatch", None, "terminal_decision without a final terminal event")
        elif last.action != record.terminal_decision and not (
            last.action.action_type == record.terminal_decision.action_type
            and record.terminal_decision.candidate_id in (None, last.candidate_id)
        ):
            add("terminal_mismatch", None, "terminal_decision differs from the last event")
    return issues


def assert_valid_record(record: EpisodeRecord) -> None:
    issues = validate_record(record)
    if issues:
        raise ProvenanceError(issues)


def verify_deterministic_source(
    record: EpisodeRecord, env_factory: Callable[[], ScientificEnvironment]
) -> list[ProvenanceIssue]:
    """Re-run the recorded actions in a fresh environment and compare public effects.

    This is the producer-side determinism check (G1/G11); replay itself never calls it.
    """
    issues: list[ProvenanceIssue] = []
    env = env_factory()
    state = env.reset(seed=record.seed)
    if state != record.initial_state:
        issues.append(ProvenanceIssue("initial_state_mismatch", None, "reset(seed) differs from record"))
        return issues
    for event in record.events:
        result = env.step(ScientificAction(**event.action.model_dump()))
        if result.observation != event.observation:
            issues.append(ProvenanceIssue("observation_mismatch", event.step, "re-run observation differs"))
        if result.state.resources != event.resources_after:
            issues.append(ProvenanceIssue("resource_mismatch", event.step, "re-run resources differ"))
    return issues


__all__ = [
    "ActionType",
    "ProvenanceError",
    "ProvenanceIssue",
    "assert_valid_record",
    "validate_record",
    "verify_deterministic_source",
]
