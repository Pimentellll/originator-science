"""Run the registered cross-family configurations with spend accounting."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from mirage.evaluation import report, runner

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_DIR = Path(__file__).resolve().parent


def _load_sibling(module_name: str, filename: str) -> Any:
    qualified_name = f"exp_cross_family_{module_name}"
    if qualified_name in sys.modules:
        return sys.modules[qualified_name]
    spec = importlib.util.spec_from_file_location(
        qualified_name, EXPERIMENT_DIR / filename
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load cross-family sibling {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module


_openai_agent = _load_sibling("openai_agent", "openai_agent.py")
OpenAIAPIError = _openai_agent.OpenAIAPIError
OpenAIResponsesAgent = _openai_agent.OpenAIResponsesAgent
OpenAIResponsesClient = _openai_agent.OpenAIResponsesClient

Y1 = ("gpt-6-luna", "high")
CONFIGS = {"Y1": Y1}
PRICES_PER_MTOK = {
    "gpt-6-luna": {
        "input": 0.10,
        "cached_input": 0.01,
        "output": 0.50,
    }
}
SPEND_CAP_USD = 2.00
STRONG_MATRIX = ROOT / "experiments" / "configs" / "eval_matrix_v1.json"
DEV_MATRIX = EXPERIMENT_DIR / "dev_matrix.json"
DEFAULT_LEDGER = EXPERIMENT_DIR / "spend_ledger.jsonl"
STRONG_OUT_ROOT = EXPERIMENT_DIR / "runs"
DEV_OUT_ROOT = ROOT / ".local" / "runs" / "cross-family"
REPORT_SLOTS = (("claude", "Y1 GPT-6 Luna high", "openai_responses"),)
CLAUDE_MODELS = {"claude": "gpt-6-luna"}
MAX_OUTPUT_TOKENS = 16_000


class SpendCapReached(Exception):
    """Raised before a request that could exceed the registered spend cap."""


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _usage_counts(usage: Any) -> dict[str, int]:
    input_tokens = int(_field(usage, "input_tokens", 0) or 0)
    details = _field(usage, "input_tokens_details", {}) or {}
    cached_tokens = int(_field(details, "cached_tokens", 0) or 0)
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": min(input_tokens, cached_tokens),
        "output_tokens": int(_field(usage, "output_tokens", 0) or 0),
    }


def cost_usd(usage: Any, model: str) -> float:
    """Calculate cost using the registered per-million-token prices."""
    prices = PRICES_PER_MTOK[model]
    counts = _usage_counts(usage)
    uncached_input = counts["input_tokens"] - counts["cached_input_tokens"]
    return (
        uncached_input * prices["input"]
        + counts["cached_input_tokens"] * prices["cached_input"]
        + counts["output_tokens"] * prices["output"]
    ) / 1_000_000


def _estimated_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = PRICES_PER_MTOK[model]
    return (
        input_tokens * prices["input"] + output_tokens * prices["output"]
    ) / 1_000_000


def _ledger_total(ledger_path: Path) -> float:
    if not ledger_path.exists():
        return 0.0
    return sum(
        float(json.loads(line)["cost_usd"])
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


class MeteredClient:
    """Responses API wrapper that records usage and enforces the spend cap."""

    def __init__(
        self,
        inner: Any,
        *,
        run_dir: Path,
        ledger_path: Path,
        run_id: str,
        config: str,
        matrix: str,
        cap: float = SPEND_CAP_USD,
    ) -> None:
        self.inner = inner
        self.responses = self
        self.run_dir = Path(run_dir)
        self.ledger_path = Path(ledger_path)
        self.run_id = run_id
        self.config = config
        self.matrix = matrix
        self.cap = cap
        self.last_input_tokens: int | None = None

    def create(self, **params: Any) -> dict[str, Any]:
        model = params["model"]
        estimate_input = (
            self.last_input_tokens + 2_000
            if self.last_input_tokens is not None
            else 8_000
        )
        projected = _estimated_cost_usd(model, estimate_input, MAX_OUTPUT_TOKENS)
        if _ledger_total(self.ledger_path) + projected > self.cap:
            raise SpendCapReached(
                f"spend cap ${self.cap:.2f} would be exceeded by the next call"
            )

        started = time.monotonic()
        response = self.inner.responses.create(**params)
        elapsed = round(time.monotonic() - started, 1)
        usage = _field(response, "usage", {}) or {}
        counts = _usage_counts(usage)
        self.last_input_tokens = counts["input_tokens"]
        response_model = _field(response, "model", model) or model
        usage_model = response_model if response_model in PRICES_PER_MTOK else model
        cost = cost_usd(usage, usage_model)
        usage_line = {
            "model": response_model,
            "response_id": _field(response, "id"),
            **counts,
            "cost_usd": cost,
            "elapsed_s": elapsed,
        }
        ledger_line = {
            "run_id": self.run_id,
            "config": self.config,
            "matrix": self.matrix,
            "model": response_model,
            **counts,
            "cost_usd": cost,
            "utc": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        _append_jsonl(self.run_dir / "usage.jsonl", usage_line)
        _append_jsonl(self.ledger_path, ledger_line)
        return response


def run_config(
    config_id: str,
    matrix_name: str,
    *,
    resume_run_id: str | None = None,
    client: Any | None = None,
    ledger_path: Path = DEFAULT_LEDGER,
    out_root: Path | None = None,
) -> Path:
    if config_id not in CONFIGS:
        raise ValueError(f"unknown configuration {config_id!r}")
    if matrix_name not in ("dev", "strong"):
        raise ValueError("matrix must be 'dev' or 'strong'")

    model, effort = CONFIGS[config_id]
    ledger_path = Path(ledger_path)
    if client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is not set; refusing to start a paid run")
        client = OpenAIResponsesClient()

    run_id = resume_run_id or (
        f"{datetime.now(UTC):%Y%m%d-%H%M}_openai_responses_{matrix_name}_{config_id}"
    )
    out_root = Path(out_root) if out_root is not None else (
        STRONG_OUT_ROOT if matrix_name == "strong" else DEV_OUT_ROOT
    )
    run_dir = out_root / run_id
    metered = MeteredClient(
        client,
        run_dir=run_dir,
        ledger_path=ledger_path,
        run_id=run_id,
        config=config_id,
        matrix=matrix_name,
    )
    matrix_path = STRONG_MATRIX if matrix_name == "strong" else DEV_MATRIX
    created_agents: list[OpenAIResponsesAgent] = []

    def make_openai_agent(
        name: str,
        prior: Any,
        reference_seeds: Any = None,
        *,
        client: Any | None = None,
        model: str | None = None,
    ) -> OpenAIResponsesAgent:
        if name != "claude":
            raise ValueError(f"unexpected agent {name!r}")
        agent = OpenAIResponsesAgent(
            client,
            model=model or CONFIGS[config_id][0],
            effort=effort,
        )
        created_agents.append(agent)
        return agent

    with patch.object(runner, "make_agent", side_effect=make_openai_agent):
        result_dir = runner.run(
            "claude",
            matrix_name,
            out_root,
            matrix=matrix_path,
            run_id=run_id,
            resume=bool(resume_run_id),
            client=metered,
            model=model,
        )

    # runner.run has no hook for provider-specific API and converted-tool metadata.
    manifest_path = result_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["api"] = "openai-responses"
    manifest["tools_sha256"] = created_agents[0].tools_sha256
    runner.write_atomic(manifest_path, runner.dumps(manifest))

    with (
        patch.object(report, "AGENT_SLOTS", REPORT_SLOTS),
        patch.object(report, "CLAUDE_MODELS", CLAUDE_MODELS),
    ):
        report.build_report({"claude": result_dir}, result_dir)
    return result_dir


def _print_spend(ledger_path: Path | None = None) -> None:
    ledger_path = Path(ledger_path) if ledger_path is not None else DEFAULT_LEDGER
    totals: dict[tuple[str, str], float] = {}
    if ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            key = (record["config"], record["matrix"])
            totals[key] = totals.get(key, 0.0) + float(record["cost_usd"])
    print(f"Total: ${sum(totals.values()):.6f}")
    for (config, matrix), amount in sorted(totals.items()):
        print(f"{config} {matrix}: ${amount:.6f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cross-family-driver")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--config", choices=tuple(CONFIGS), required=True)
    run_parser.add_argument("--matrix", choices=("dev", "strong"), required=True)
    run_parser.add_argument("--resume", metavar="RUN_ID")
    commands.add_parser("spend")
    args = parser.parse_args(argv)

    if args.command == "spend":
        _print_spend()
        return 0
    try:
        run_dir = run_config(
            args.config,
            args.matrix,
            resume_run_id=args.resume,
        )
    except (
        OpenAIAPIError,
        SpendCapReached,
        ValueError,
        FileExistsError,
        FileNotFoundError,
    ) as err:
        print(f"cross-family: {err}", file=sys.stderr)
        return 2
    print(run_dir)
    print(f"Ledger total: ${_ledger_total(DEFAULT_LEDGER):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
