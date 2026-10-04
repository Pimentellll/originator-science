"""Public-safe system catalogue for the receptor-binder API: policies, demo scenarios,
scenario-version selection, the terminal verdict adapter and the system self-checks.

The scenario catalogue is orchestration metadata for the human running a demo. It is served
so the cockpit can offer a launcher; it is never passed to a policy, belief, record or replay.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from mirage.api.meta import CheckDTO, PolicyInfoDTO, ScenarioInfoDTO, SelfCheck, SystemCatalogue
from mirage.environments.binder import BinderBioPOMDP, BinderWorldMode
from mirage.environments.binder.scenarios import SHOWCASE_SCENARIOS, BinderScenarioVersion
from mirage.evaluation.campaign import CampaignEvaluator
from mirage.integration.profiles import ScientificProfile
from mirage.provenance import PublicRecordStore, Replay, find_privileged_fields

# Human-facing titles for the five showcase worlds. Descriptions come from the scenario catalogue.
_TITLES = {
    "instability": "Folding instability",
    "aggregation_kinetic_defect": "Aggregation + kinetic defect",
    "broken_assay": "Broken assay",
    "invalid_biological_model": "Invalid biological model",
    "misleading_proxy_trap": "Misleading proxy trap",
}

_POLICIES = (
    ("rescue_planner", "Rescue Planner", "domain_expert", "Protects later kinetic evidence: runs SEC first and redesigns for solubility when aggregation is severe, then measures SPR."),
    ("greedy_eig", "Greedy EIG", "myopic_planner", "Picks the single action with the highest expected information gain per unit cost from the particle belief."),
    ("fixed_pipeline", "Fixed Pipeline", "scripted_baseline", "Runs a fixed assay order regardless of what has been learned."),
    ("random", "Random", "random", "Chooses uniformly among legal non-terminal actions. A floor for comparison."),
)
_NOT_WIRED = (
    ("lookahead", "Lookahead", "lookahead_planner", "Multi-step planner over the belief.", "Implemented for offline benchmarking; not wired into the live API."),
    ("ppo", "PPO", "learned_policy", "Learned masked-PPO policy.", "No validated checkpoint is served; not wired into the live API."),
)


def resolve_world(scenario: str | None, default: BinderWorldMode) -> BinderWorldMode:
    """Accept a showcase id (``broken_assay``) or a world-mode name (``ASSAY_FAILURE``)."""
    if scenario is None:
        return default
    for item in SHOWCASE_SCENARIOS:
        if scenario in (item.name, item.world_mode.value):
            return item.world_mode
    raise ValueError("unknown scenario")


def make_scenario_factory(default_world: BinderWorldMode, default_version: BinderScenarioVersion):
    def factory(scenario: str | None, version: str | None):
        world = resolve_world(scenario, default_world)
        resolved = BinderScenarioVersion(version) if version else default_version
        return BinderBioPOMDP(world, scenario_version=resolved), resolved.value

    return factory


def verdict_from_evaluation(record, env) -> dict:
    """Run the privileged evaluator. The caller (the token-gated route) allow-lists the keys."""
    from mirage.integration.controller import _BinderOracle

    return CampaignEvaluator().evaluate(record, _BinderOracle(env)).model_dump(mode="json")


def policy_catalogue(registered: tuple[str, ...]) -> tuple[PolicyInfoDTO, ...]:
    out = [
        PolicyInfoDTO(name=n, display_name=d, kind=k, available=n in registered, description=desc,
                      reason=None if n in registered else "Not registered on this server.")
        for n, d, k, desc in _POLICIES
    ]
    out += [PolicyInfoDTO(name=n, display_name=d, kind=k, available=False, description=desc, reason=why)
            for n, d, k, desc, why in _NOT_WIRED]
    return tuple(out)


def scenario_catalogue(default_world: BinderWorldMode | None = None) -> tuple[ScenarioInfoDTO, ...]:
    return tuple(
        ScenarioInfoDTO(id=s.name, title=_TITLES.get(s.name, s.name), summary=s.description, cli_name=s.world_mode.value,
                        is_default=s.world_mode == default_world)
        for s in SHOWCASE_SCENARIOS
    )


def run_selfchecks(default_world: BinderWorldMode, version: BinderScenarioVersion) -> tuple[CheckDTO, ...]:
    """Real checks against the real stack, run once and cached. Never reads privileged state
    into the response: only pass/fail and public counts leave this function."""
    from mirage.integration.controller import CampaignController

    checks: list[CheckDTO] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append(CheckDTO(name=name, status="pass" if ok else "fail", detail=detail))

    try:
        BinderBioPOMDP(default_world, scenario_version=version).reset(9)
        add("environment", True, f"initialised (seed 9, {version.value})")
    except Exception as exc:  # noqa: BLE001 - a diagnostic must report, not raise
        add("environment", False, f"{type(exc).__name__}")
        return tuple(checks)

    def run(root: Path):
        c = CampaignController(PublicRecordStore(root))
        c.reset(9, default_world, ScientificProfile.RECEPTOR_BINDER_RESCUE, "rescue_planner")
        payloads = []
        for _ in range(12):
            step = c.step()
            payloads.append(step.dto.model_dump(mode="json"))
            if step.terminal:
                break
        return c, payloads

    try:
        with tempfile.TemporaryDirectory(prefix="mirage-selfcheck-") as a, tempfile.TemporaryDirectory(prefix="mirage-selfcheck-") as b:
            first, payloads = run(Path(a))
            second, _ = run(Path(b))
            record = first.record()
            same = record.model_dump(mode="json") == second.record().model_dump(mode="json")
            add("deterministic_smoke", same and record.terminal_decision is not None,
                f"seed 9 · {len(record.events)} events · {'identical' if same else 'DIFFERENT'} on re-run")
            loaded = first.store.load(first.episode_id)
            frames = tuple(Replay(loaded))
            add("record_replay", loaded.model_dump(mode="json") == record.model_dump(mode="json") and len(frames) == len(record.events),
                f"stored record reloads; {len(frames)} replay frames")
            planted = bool(find_privileged_fields({"ground_truth": 1}))
            clean = not any(find_privileged_fields(p) for p in payloads)
            add("leak_guard", planted and clean, "planted privileged key detected; real step payloads clean")
    except Exception as exc:  # noqa: BLE001
        add("deterministic_smoke", False, f"{type(exc).__name__}")
    return tuple(checks)


def receptor_binder_catalogue(service, default_world: BinderWorldMode, version: BinderScenarioVersion) -> SystemCatalogue:
    return SystemCatalogue(
        policies=policy_catalogue(service.policy_names),
        scenarios=scenario_catalogue(default_world),
        semantics_default=version.value,
        semantics_available=tuple(v.value for v in BinderScenarioVersion),
        selfcheck=SelfCheck(lambda: run_selfchecks(default_world, version)),
    )
