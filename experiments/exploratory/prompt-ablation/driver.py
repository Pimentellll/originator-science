"""Driver for the exploratory prompt cue ablation (REGISTRATION.md).

Reuses the frozen runner pieces (matrix loading, Gate 0 D_diag, ``run_episode``, the
evaluator, ``summarize``) and subclasses the frozen ``ClaudeAgent``. Only the system prompt,
the tool descriptions and (prompt-v2-minimal) the observation ``assay`` string differ.

Usage (from the repo root, PYTHONPATH=src):
  .venv/bin/python experiments/exploratory/prompt-ablation/driver.py run \
      --variant prompt-v2-noceiling --matrix strong --model claude-sonnet-5-5 \
      --out experiments/exploratory/prompt-ablation/runs
  .venv/bin/python experiments/exploratory/prompt-ablation/driver.py run \
      --variant prompt-v2-noceiling --matrix dev2 \
      --matrix-file experiments/exploratory/prompt-ablation/dev_matrix.json \
      --model claude-sonnet-5-5 --out experiments/exploratory/prompt-ablation/dryrun
  .venv/bin/python experiments/exploratory/prompt-ablation/driver.py report RUN_DIR
  .venv/bin/python experiments/exploratory/prompt-ablation/driver.py spend
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mirage.agents import claude as claude_mod  # noqa: E402
from mirage.agents.claude import ClaudeAgent  # noqa: E402
from mirage.config import canonical_sha256, load_prior, sample_episode  # noqa: E402
from mirage.evaluation import report, runner  # noqa: E402
from mirage.lab.tools import MAX_TURNS  # noqa: E402

from variants import VARIANTS, PromptVariant  # noqa: E402

DEFAULT_MODEL = "claude-sonnet-5-5"  # C2; never substituted
EXP_ROOT = HERE
FROZEN_RESULTS = runner.ROOT / "experiments" / "results"
FROZEN_C2 = FROZEN_RESULTS / "20261004-0049_claude_strong"
USAGE_FILE = "usage.jsonl"

# Public Anthropic pricing for Claude Sonnet 5.5, USD per million tokens (REGISTRATION §7).
PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.20, "cache_write": 2.50},
}
SESSION_STOP_USD = 4.50  # hard cap is $5.00; stop margin
EPISODE_ALLOWANCE_USD = 0.15


class BudgetExceeded(RuntimeError):
    pass


def call_cost(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0,
              cache_write: int = 0) -> float:
    p = PRICING_USD_PER_MTOK[model]
    return (input_tokens * p["input"] + output_tokens * p["output"]
            + cache_read * p["cache_read"] + cache_write * p["cache_write"]) / 1e6


def usage_files(root: Path = EXP_ROOT) -> list[Path]:
    return sorted(root.rglob(USAGE_FILE))


def spent_usd(root: Path = EXP_ROOT) -> float:
    total = 0.0
    for path in usage_files(root):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                u = json.loads(line)
                total += call_cost(u["model"], u["input_tokens"], u["output_tokens"],
                                   u.get("cache_read", 0), u.get("cache_write", 0))
    return total


class Ledger:
    """Session spend: everything already logged under ``root`` plus calls made now."""

    def __init__(self, root: Path = EXP_ROOT, stop_usd: float = SESSION_STOP_USD) -> None:
        self.stop_usd = stop_usd
        self.spent = spent_usd(root)

    def add(self, usd: float) -> None:
        self.spent += usd

    def allows(self, allowance: float) -> bool:
        return self.spent + allowance <= self.stop_usd

    def check_call(self) -> None:
        if self.spent >= self.stop_usd:
            raise BudgetExceeded(f"spend ${self.spent:.4f} reached stop ${self.stop_usd:.2f}")


class MeteredClient:
    """Wraps an Anthropic client; appends token usage per call to ``usage.jsonl``."""

    def __init__(self, inner: Any, usage_path: Path, ledger: Ledger) -> None:
        self._inner = inner
        self._usage_path = usage_path
        self._ledger = ledger
        self.messages = self

    def create(self, **params: Any) -> Any:
        self._ledger.check_call()
        t0 = time.perf_counter()
        response = self._inner.messages.create(**params)
        u = response.usage
        line = {
            "model": response.model,
            "stop_reason": response.stop_reason,
            "input_tokens": int(u.input_tokens or 0),
            "output_tokens": int(u.output_tokens or 0),
            "cache_read": int(getattr(u, "cache_read_input_tokens", 0) or 0),
            "cache_write": int(getattr(u, "cache_creation_input_tokens", 0) or 0),
            "s": round(time.perf_counter() - t0, 1),
        }
        self._usage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._usage_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, sort_keys=False) + "\n")
        model = line["model"] if line["model"] in PRICING_USD_PER_MTOK else params["model"]
        self._ledger.add(call_cost(model, line["input_tokens"], line["output_tokens"],
                                   line["cache_read"], line["cache_write"]))
        return response


@contextmanager
def _observation_renderer(render: Any) -> Iterator[None]:
    """Swap the renderer the frozen ClaudeAgent.run looks up, and always restore it."""
    original = claude_mod.render_observation
    claude_mod.render_observation = render
    try:
        yield
    finally:
        claude_mod.render_observation = original


class VariantClaudeAgent(ClaudeAgent):
    """Frozen ClaudeAgent with a different system prompt / tool descriptions / assay string."""

    def __init__(self, variant: PromptVariant, client: Any | None = None, *,
                 model: str = DEFAULT_MODEL, max_turns: int = MAX_TURNS) -> None:
        super().__init__(client, model=model, max_turns=max_turns)
        self.variant = variant
        self.prompt_version = variant.version
        self.prompt_sha256 = variant.sha256()

    def request_params(self, messages: list[Any]) -> dict[str, Any]:
        params = super().request_params(messages)
        params["system"] = self.variant.system
        params["tools"] = self.variant.tools
        return params

    def run(self, session: Any) -> None:
        render = self.variant.render_observation()
        if render is claude_mod.render_observation:
            return super().run(session)
        with _observation_renderer(render):
            return super().run(session)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_variant(variant_name: str, matrix_name: str, out_root: Path, *,
                matrix_file: Path = runner.MATRIX, model: str = DEFAULT_MODEL,
                client: Any | None = None, run_id: str | None = None, resume: bool = False,
                ledger: Ledger | None = None,
                episode_allowance: float = EPISODE_ALLOWANCE_USD) -> Path:
    """Mirror of ``runner.run`` for the Claude agent with a prompt variant."""
    if variant_name not in VARIANTS:
        raise ValueError(f"unknown variant {variant_name!r}; expected one of {sorted(VARIANTS)}")
    if model not in PRICING_USD_PER_MTOK:
        raise ValueError(f"no pricing registered for {model!r}; refusing to run unmetered")
    variant = VARIANTS[variant_name]
    prior = load_prior(runner.SCENARIO)
    dset = runner.frozen_dset(prior, runner.GATE0_SUMMARY)
    cfgs = [sample_episode(prior, seed, condition)
            for seed, condition in runner.load_matrix(matrix_file, matrix_name)]
    if client is None and not os.environ.get(runner.API_KEY_ENV):
        raise ValueError(f"{runner.API_KEY_ENV} is not set; refusing to start a paid run")
    if resume and not run_id:
        raise ValueError("--resume needs the RUN_ID of the run to continue")
    run_id = run_id or f"{datetime.now(timezone.utc):%Y%m%d-%H%M}_claude_{variant_name}_{matrix_name}"
    run_dir = out_root / run_id
    if run_dir.exists() and not resume:
        raise FileExistsError(f"{run_dir} already exists; runs are never overwritten")
    ledger = ledger if ledger is not None else Ledger()
    inner = client if client is not None else claude_mod.make_client()
    metered = MeteredClient(inner, run_dir / USAGE_FILE, ledger)
    agent = VariantClaudeAgent(variant, metered, model=model)
    manifest = {
        "run_id": run_id, "agent": "claude", "matrix": matrix_name,
        "matrix_sha256": runner.file_sha256(matrix_file),
        "scenario_sha256": canonical_sha256(prior),
        "gate0_summary_sha256": runner.file_sha256(runner.GATE0_SUMMARY),
        "diagnostic_action_set": dset.model_dump(mode="json"),
        "prompt_version": variant.version, "prompt_sha256": variant.sha256(),
        "model": agent.model, "effort": agent.effort,
        "n_episodes": len(cfgs), "versions": runner.versions(), "created_at": _now(),
        "exploratory": True,
        "driver": "experiments/exploratory/prompt-ablation/driver.py",
        "variant_notes": variant.notes,
        "pricing_usd_per_mtok": PRICING_USD_PER_MTOK[model],
    }
    manifest_path = run_dir / "manifest.json"
    if resume:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        ignore = ("created_at", "versions", "reruns", "stopped_early")
        changed = sorted(k for k in manifest if k not in ignore and manifest[k] != old.get(k))
        if changed:
            raise ValueError(f"cannot resume {run_id}: manifest differs in {', '.join(changed)}")
        base = {k: v for k, v in old.items() if k != "stopped_early"}
    else:
        runner.write_atomic(manifest_path, runner.dumps(manifest))
        base = manifest
    meta = {"run_id": run_id}
    stopped: str | None = None
    for cfg in cfgs:
        episode_path = run_dir / "episodes" / f"{cfg.episode_id}.json"
        attempt1 = run_dir / "reruns" / f"{cfg.episode_id}.attempt1.json"
        if resume and episode_path.exists():
            continue
        if not ledger.allows(episode_allowance):
            stopped = (f"spend ${ledger.spent:.4f} + allowance ${episode_allowance:.2f} > "
                       f"stop ${ledger.stop_usd:.2f} before {cfg.episode_id}")
            break
        rerun_in_progress = resume and attempt1.exists()
        res = runner.run_episode(cfg, agent, dset, meta)
        if res.status == "API_FAILURE" and not rerun_in_progress:
            runner.write_atomic(attempt1, runner.dumps(res.model_dump(mode="json")))
            res = runner.run_episode(cfg, agent, dset, meta)
        runner.write_atomic(episode_path, runner.dumps(res.model_dump(mode="json")))
        print(f"{cfg.episode_id}: {res.status} correct={res.scores.correct} "
              f"control={res.scores.diagnostic_control} spend=${ledger.spent:.4f}", flush=True)
    reruns = {p.name.removesuffix(".attempt1.json"): f"reruns/{p.name}"
              for p in sorted((run_dir / "reruns").glob("*.attempt1.json"))}
    final = {**base, "reruns": reruns}
    if stopped:
        final["stopped_early"] = stopped
    runner.write_atomic(manifest_path, runner.dumps(final))
    if any((run_dir / "episodes").glob("*.json")):
        runner.summarize(run_dir)
    return run_dir


@contextmanager
def _relabel_c2(label: str) -> Iterator[None]:
    """The frozen report has fixed agent slots; show the variant run in the Sonnet slot under
    an honest label. Restores the frozen slots afterwards."""
    original = report.AGENT_SLOTS
    report.AGENT_SLOTS = tuple((k, label if k == "claude_c2" else l, a) for k, l, a in original)
    try:
        yield
    finally:
        report.AGENT_SLOTS = original


def write_run_report(run_dir: Path) -> tuple[Path, Path]:
    """results.md + results.png for one variant run, via the frozen report module."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    label = f"Sonnet 5.5 {manifest['prompt_version']}"
    run_dirs: dict[str, Path | None] = {"claude_c2": run_dir}
    if manifest["matrix"] == "strong":  # frozen baselines on the same matrix, read only
        run_dirs |= {"good_scientist": FROZEN_RESULTS / "20261003-2333_good_scientist_strong",
                     "passive_bayes": FROZEN_RESULTS / "20261003-2333_passive_bayes_strong"}
    with _relabel_c2(label):
        return report.build_report(run_dirs, run_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="prompt-ablation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--variant", choices=sorted(VARIANTS), required=True)
    r.add_argument("--matrix", required=True)
    r.add_argument("--matrix-file", type=Path, default=runner.MATRIX)
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--resume", metavar="RUN_ID")
    rep = sub.add_parser("report")
    rep.add_argument("run_dir", type=Path)
    sub.add_parser("spend")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        try:
            path = run_variant(args.variant, args.matrix, args.out,
                               matrix_file=args.matrix_file, model=args.model,
                               run_id=args.resume, resume=bool(args.resume))
        except (FileNotFoundError, ValueError, FileExistsError) as err:
            print(f"prompt-ablation: {err}", file=sys.stderr)
            return 2
        print(path)
        print(f"session spend so far: ${spent_usd():.4f}")
    elif args.cmd == "report":
        for p in write_run_report(args.run_dir):
            print(p)
    else:
        for p in usage_files():
            print(f"{p.relative_to(EXP_ROOT)}: ${spent_usd(p.parent):.4f}")
        print(f"total: ${spent_usd():.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
