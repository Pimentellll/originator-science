"""Run registered prompt-ablation arms with a session-wide spend ledger."""

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

ROOT = Path(__file__).resolve().parents[3]
PROMPT_DIR = Path(__file__).resolve().parent
if str(PROMPT_DIR) not in sys.path:
    sys.path.insert(0, str(PROMPT_DIR))

from prompts import PROMPTS, variant_sha256

from mirage.agents.claude import ClaudeAgent, make_client
from mirage.evaluation import report, runner

MODEL = "claude-sonnet-5-5"
SPEND_CAP_USD = 5.0
PRICES_PER_MTOK = {
    "claude-sonnet-5-5": {
        "input": 2.0,
        "output": 10.0,
        "cache_write_5m": 2.5,
        "cache_write_1h": 4.0,
        "cache_read": 0.2,
    }
}
STRONG_MATRIX = ROOT / "experiments" / "configs" / "eval_matrix_v1.json"
DEV_MATRIX = PROMPT_DIR / "dev_matrix.json"
DEFAULT_LEDGER = PROMPT_DIR / "spend_ledger.jsonl"
STRONG_OUT_ROOT = PROMPT_DIR / "runs"
DEV_OUT_ROOT = ROOT / ".local" / "runs" / "prompt-ablation"


class SpendCapReached(Exception):
    """Raised before an API call that could exceed the registered spend cap."""


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


def cost_usd(usage_dict: dict[str, Any], model: str) -> float:
    """Return the listed model cost for a Messages API usage object or mapping."""
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
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


class MeteredClient:
    """Messages API wrapper that records usage and guards each call against the cap."""

    def __init__(
        self,
        inner: Any,
        *,
        run_dir: Path,
        ledger_path: Path,
        run_id: str,
        arm: str,
        matrix: str,
        cap: float = SPEND_CAP_USD,
    ) -> None:
        self.inner = inner
        self.messages = self
        self.run_dir = Path(run_dir)
        self.ledger_path = Path(ledger_path)
        self.run_id = run_id
        self.arm = arm
        self.matrix = matrix
        self.cap = cap
        self.last_input_tokens: int | None = None

    def create(self, **params: Any) -> Any:
        estimate_input = (
            self.last_input_tokens + 2_000
            if self.last_input_tokens is not None
            else 8_000
        )
        prices = PRICES_PER_MTOK[params.get("model", MODEL)]
        projected = (
            estimate_input * prices["cache_write_1h"] + 16_000 * prices["output"]
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
        creation_tokens = (
            counts["cache_creation_ephemeral_5m_input_tokens"]
            + counts["cache_creation_ephemeral_1h_input_tokens"]
        )
        model = _field(response, "model", params.get("model", MODEL))
        stop_reason = _field(response, "stop_reason")
        usage_line = {
            "model": model,
            "stop_reason": stop_reason,
            "input_tokens": counts["input_tokens"],
            "output_tokens": counts["output_tokens"],
            "cache_read": counts["cache_read_input_tokens"],
            "cache_write": creation_tokens,
            "s": elapsed,
        }
        ledger_line = {
            "run_id": self.run_id,
            "arm": self.arm,
            "matrix": self.matrix,
            "model": model,
            **counts,
            "cost_usd": cost_usd(usage, model),
            "utc": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        _append_jsonl(self.run_dir / "usage.jsonl", usage_line)
        _append_jsonl(self.ledger_path, ledger_line)
        return response


class VariantClaudeAgent(ClaudeAgent):
    """Claude adapter using a frozen alternative system prompt."""

    def __init__(self, client: Any, *, model: str, prompt_version: str) -> None:
        super().__init__(client, model=model)
        self.prompt_version = prompt_version
        self.prompt_sha256 = variant_sha256(PROMPTS[prompt_version])

    def request_params(self, messages: list[Any]) -> dict[str, Any]:
        params = super().request_params(messages)
        params["system"] = PROMPTS[self.prompt_version]
        return params


def run_arm(
    prompt_version: str,
    matrix: str,
    *,
    out_root: Path | None = None,
    run_id: str | None = None,
    resume: bool = False,
    client: Any | None = None,
    ledger_path: Path | None = None,
) -> Path:
    if prompt_version not in PROMPTS:
        raise ValueError(f"unknown prompt variant {prompt_version!r}")
    if matrix not in ("dev", "strong"):
        raise ValueError("matrix must be 'dev' or 'strong'")

    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError(
                "ANTHROPIC_API_KEY is not set; refusing to start a paid run"
            )
        client = make_client()

    suffix = prompt_version.removeprefix("prompt-v2-")
    run_id = run_id or (
        f"{datetime.now(UTC):%Y%m%d-%H%M}_claude_{suffix}_{matrix}"
    )
    out_root = Path(out_root) if out_root is not None else (
        STRONG_OUT_ROOT if matrix == "strong" else DEV_OUT_ROOT
    )
    run_dir = out_root / run_id
    ledger_path = Path(ledger_path) if ledger_path is not None else DEFAULT_LEDGER
    metered = MeteredClient(
        client,
        run_dir=run_dir,
        ledger_path=ledger_path,
        run_id=run_id,
        arm=prompt_version,
        matrix=matrix,
    )
    matrix_path = STRONG_MATRIX if matrix == "strong" else DEV_MATRIX

    def make_variant_agent(
        name: str,
        prior: Any,
        reference_seeds: Any = None,
        *,
        client: Any | None = None,
        model: str | None = None,
    ) -> VariantClaudeAgent:
        if name != "claude":
            raise ValueError(f"unexpected agent {name!r}")
        return VariantClaudeAgent(
            client, model=model or MODEL, prompt_version=prompt_version
        )

    with (
        patch.object(runner, "make_agent", side_effect=make_variant_agent),
        patch.object(runner, "PROMPT_VERSION", prompt_version),
    ):
        result_dir = runner.run(
            "claude",
            matrix,
            out_root,
            matrix=matrix_path,
            client=metered,
            model=MODEL,
            run_id=run_id,
            resume=resume,
        )

    slots = ((
        "claude_c2",
        f"Sonnet 5.5 {prompt_version}",
        "claude",
    ),)
    try:
        with patch.object(report, "AGENT_SLOTS", slots):
            report.build_report({"claude_c2": result_dir}, result_dir)
    except (OSError, TypeError, ValueError) as err:
        print(f"prompt-ablation: report generation skipped: {err}", file=sys.stderr)
    return result_dir


def _print_spend(ledger_path: Path | None = None) -> None:
    ledger_path = ledger_path or DEFAULT_LEDGER
    totals: dict[str, float] = {}
    if ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            run_id = record["run_id"]
            totals[run_id] = totals.get(run_id, 0.0) + float(record["cost_usd"])
    print(f"Total: ${sum(totals.values()):.6f}")
    for run_id, amount in sorted(totals.items()):
        print(f"{run_id}: ${amount:.6f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prompt-ablation-driver")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument(
        "--prompt", choices=tuple(PROMPTS), required=True
    )
    run_parser.add_argument("--matrix", choices=("dev", "strong"), required=True)
    run_parser.add_argument("--resume", metavar="RUN_ID")
    commands.add_parser("spend")
    args = parser.parse_args(argv)

    if args.command == "spend":
        _print_spend()
        return 0
    try:
        run_dir = run_arm(
            args.prompt,
            args.matrix,
            run_id=args.resume,
            resume=args.resume is not None,
        )
    except (SpendCapReached, ValueError) as err:
        print(f"prompt-ablation: {err}", file=sys.stderr)
        return 2
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
