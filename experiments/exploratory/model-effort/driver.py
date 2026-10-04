"""Run model-effort configurations with usage logging and a session spend guard."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from mirage.agents.claude import ClaudeAgent, make_client
from mirage.evaluation import report, runner

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_DIR = Path(__file__).resolve().parent
CONFIGS = {
    "X1": ("claude-haiku-4-5-20251001", "high"),
    "X2": ("claude-sonnet-5-5", "low"),
    "X3": ("claude-opus-5-5", "low"),
}
CONFIG_LABELS = {
    "X1": "X1 Haiku 4.5 high",
    "X2": "X2 Sonnet 5.5 low",
    "X3": "X3 Opus 5.5 low",
}
PRICES_PER_MTOK = {
    "claude-haiku-4-5-20251001": {
        "input": 1.0,
        "output": 5.0,
        "cache_write_5m": 1.25,
        "cache_write_1h": 2.0,
        "cache_read": 0.10,
    },
    "claude-sonnet-5-5": {
        "input": 2.0,
        "output": 10.0,
        "cache_write_5m": 2.50,
        "cache_write_1h": 4.0,
        "cache_read": 0.20,
    },
    "claude-opus-5-5": {
        "input": 4.0,
        "output": 20.0,
        "cache_write_5m": 5.0,
        "cache_write_1h": 8.0,
        "cache_read": 0.20,
    },
}
SPEND_CAP_USD = 5.0
X3_MIN_REMAINING_USD = 2.90
STRONG_MATRIX = ROOT / "experiments" / "configs" / "eval_matrix_v1.json"
DEV_MATRIX = EXPERIMENT_DIR / "dev_matrix.json"
DEFAULT_LEDGER = EXPERIMENT_DIR / "spend_ledger.jsonl"
STRONG_OUT_ROOT = EXPERIMENT_DIR / "runs"
DEV_OUT_ROOT = ROOT / ".local" / "runs" / "model-effort"


class SpendCapReached(Exception):
    """Raised before a request that could exceed the session spend cap."""


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _usage_counts(usage: Any) -> dict[str, int]:
    creation = _field(usage, "cache_creation")
    cache_5m = _field(creation, "ephemeral_5m_input_tokens")
    cache_1h = _field(creation, "ephemeral_1h_input_tokens")
    if cache_5m is None and cache_1h is None:
        cache_5m = _field(usage, "cache_creation_input_tokens", 0)
        cache_1h = 0
    return {
        "input_tokens": int(_field(usage, "input_tokens", 0) or 0),
        "output_tokens": int(_field(usage, "output_tokens", 0) or 0),
        "cache_read_input_tokens": int(
            _field(usage, "cache_read_input_tokens", 0) or 0
        ),
        "cache_creation_ephemeral_5m_input_tokens": int(cache_5m or 0),
        "cache_creation_ephemeral_1h_input_tokens": int(cache_1h or 0),
    }


def cost_usd(usage_dict: Any, model: str) -> float:
    """Calculate request cost using the registered per-million-token prices."""
    prices = PRICES_PER_MTOK[model]
    counts = _usage_counts(usage_dict)
    return (
        counts["input_tokens"] * prices["input"]
        + counts["output_tokens"] * prices["output"]
        + counts["cache_read_input_tokens"] * prices["cache_read"]
        + counts["cache_creation_ephemeral_5m_input_tokens"]
        * prices["cache_write_5m"]
        + counts["cache_creation_ephemeral_1h_input_tokens"]
        * prices["cache_write_1h"]
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
    """Messages client wrapper that records usage and enforces the spend cap."""

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
        self.messages = self
        self.run_dir = Path(run_dir)
        self.ledger_path = Path(ledger_path)
        self.run_id = run_id
        self.config = config
        self.matrix = matrix
        self.cap = cap
        self.last_input_tokens: int | None = None

    def create(self, **params: Any) -> Any:
        estimate_input = (
            self.last_input_tokens + 2_000
            if self.last_input_tokens is not None
            else 8_000
        )
        model = params["model"]
        prices = PRICES_PER_MTOK[model]
        projected = (
            estimate_input * prices["input"] + 16_000 * prices["output"]
        ) / 1_000_000
        if _ledger_total(self.ledger_path) + projected > self.cap:
            raise SpendCapReached(
                f"spend cap ${self.cap:.2f} would be exceeded by the next call"
            )

        started = time.monotonic()
        response = self.inner.messages.create(**params)
        elapsed = round(time.monotonic() - started, 1)
        usage = _field(response, "usage", {})
        counts = _usage_counts(usage)
        self.last_input_tokens = counts["input_tokens"]
        cache_write = (
            counts["cache_creation_ephemeral_5m_input_tokens"]
            + counts["cache_creation_ephemeral_1h_input_tokens"]
        )
        response_model = _field(response, "model", model)
        usage_line = {
            "model": response_model,
            "stop_reason": _field(response, "stop_reason"),
            "input_tokens": counts["input_tokens"],
            "output_tokens": counts["output_tokens"],
            "cache_read": counts["cache_read_input_tokens"],
            "cache_write": cache_write,
            "s": elapsed,
        }
        ledger_line = {
            "run_id": self.run_id,
            "config": self.config,
            "matrix": self.matrix,
            "model": response_model,
            **counts,
            "cost_usd": cost_usd(
                usage, response_model if response_model in PRICES_PER_MTOK else model
            ),
            "utc": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        _append_jsonl(self.run_dir / "usage.jsonl", usage_line)
        _append_jsonl(self.ledger_path, ledger_line)
        return response


class EffortClaudeAgent(ClaudeAgent):
    """Claude adapter configured with the selected reasoning effort."""

    def __init__(self, client: Any, *, model: str, effort: str | None) -> None:
        super().__init__(client, model=model)
        self.effort = effort

    def request_params(self, messages: list[Any]) -> dict[str, Any]:
        params = super().request_params(messages)
        if self.effort is None:
            params.pop("output_config")
        else:
            params["output_config"] = {"effort": self.effort}
        return params


def run_config(
    config_id: str,
    matrix_name: str,
    *,
    no_effort: bool = False,
    resume_run_id: str | None = None,
    client: Any | None = None,
    ledger_path: Path = DEFAULT_LEDGER,
    out_root: Path | None = None,
) -> Path:
    if config_id not in CONFIGS:
        raise ValueError(f"unknown configuration {config_id!r}")
    if matrix_name not in ("dev", "strong"):
        raise ValueError("matrix must be 'dev' or 'strong'")
    if no_effort and config_id != "X1":
        raise ValueError("no_effort is only allowed for X1")

    model, configured_effort = CONFIGS[config_id]
    effort = None if no_effort else configured_effort
    ledger_path = Path(ledger_path)
    ledger_total = _ledger_total(ledger_path)
    if (
        config_id == "X3"
        and resume_run_id is None
        and SPEND_CAP_USD - ledger_total < X3_MIN_REMAINING_USD
    ):
        raise ValueError(
            f"X3 requires at least ${X3_MIN_REMAINING_USD:.2f} remaining "
            "in the spend cap"
        )

    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError(
                "ANTHROPIC_API_KEY is not set; refusing to start a paid run"
            )
        client = make_client()

    run_id = resume_run_id or (
        f"{datetime.now(UTC):%Y%m%d-%H%M}_claude_{matrix_name}_{config_id}"
        + ("-noeffort" if no_effort else "")
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

    def make_effort_agent(
        name: str,
        prior: Any,
        reference_seeds: Any = None,
        *,
        client: Any | None = None,
        model: str | None = None,
    ) -> EffortClaudeAgent:
        if name != "claude":
            raise ValueError(f"unexpected agent {name!r}")
        return EffortClaudeAgent(
            client,
            model=model or CONFIGS[config_id][0],
            effort=effort,
        )

    with patch.object(runner, "make_agent", side_effect=make_effort_agent):
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

    slots = (("claude", CONFIG_LABELS[config_id], "claude"),)
    with (
        patch.object(report, "AGENT_SLOTS", slots),
        patch.object(report, "CLAUDE_MODELS", {"claude": model}),
    ):
        report.build_report({"claude": result_dir}, result_dir)
    return result_dir


def _print_spend(ledger_path: Path = DEFAULT_LEDGER) -> None:
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
    parser = argparse.ArgumentParser(prog="model-effort-driver")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--config", choices=tuple(CONFIGS), required=True)
    run_parser.add_argument("--matrix", choices=("dev", "strong"), required=True)
    run_parser.add_argument("--no-effort", action="store_true")
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
            no_effort=args.no_effort,
            resume_run_id=args.resume,
        )
    except (SpendCapReached, ValueError, FileExistsError, FileNotFoundError) as err:
        print(f"model-effort: {err}", file=sys.stderr)
        return 2
    print(run_dir)
    print(f"Ledger total: ${_ledger_total(DEFAULT_LEDGER):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
