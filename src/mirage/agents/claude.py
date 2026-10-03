"""Claude adapter: manual Messages API tool-use loop (DESIGN §9.4, §19).

Visible side only: imports nothing hidden (DESIGN §12). The runner reads ``outcome`` and
``transcript`` after ``run`` to set API_FAILURE / REFUSED and fill ``llm_transcript``.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import anthropic

from mirage.agents.base import LabSession
from mirage.lab.tools import (
    MAX_TURNS,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
    prompt_sha256,
    render_observation,
)

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 16_000
EFFORT = "high"
MAX_RETRIES = 4
TIMEOUT_S = 120.0
TOOL_CHOICE = {"type": "auto", "disable_parallel_tool_use": True}
REMINDER = "Continue. Use the tools, and finish by calling submit_diagnosis."

Outcome = Literal["API_FAILURE", "REFUSED"] | None


def make_client() -> anthropic.Anthropic:
    """SDK client; credentials are resolved by the SDK and never logged."""
    return anthropic.Anthropic(max_retries=MAX_RETRIES, timeout=TIMEOUT_S)


class ClaudeAgent:
    """One episode per ``run``. Never substitutes a model; the client is injectable for tests."""

    name = "claude"
    kind = "llm"

    def __init__(self, client: Any | None = None, *, model: str = DEFAULT_MODEL,
                 max_turns: int = MAX_TURNS) -> None:
        self._client = client
        self.model = model
        self.effort = EFFORT
        self.max_turns = max_turns
        self.prompt_version = PROMPT_VERSION
        self.prompt_sha256 = prompt_sha256()
        self.sdk_version = anthropic.__version__
        self.outcome: Outcome = None
        self.reason: str | None = None
        self.transcript: list[dict[str, Any]] = []

    def request_params(self, messages: list[Any]) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": TOOL_CHOICE,
            "output_config": {"effort": self.effort},
            "messages": messages,
        }

    def _log(self, kind: str, **fields: Any) -> None:
        self.transcript.append({"kind": kind, **fields})

    def run(self, session: LabSession) -> None:
        client = self._client if self._client is not None else make_client()
        self.outcome, self.reason, self.transcript = None, None, []
        first = render_observation(session.observation())
        messages: list[Any] = [{"role": "user", "content": first}]
        self._log("user", content=first)
        turn = 0
        while turn < self.max_turns and not session.finished:
            turn += 1
            params = self.request_params(messages)
            logged = {k: v for k, v in params.items() if k not in ("messages", "system", "tools")}
            try:
                response = client.messages.create(**params)
            except anthropic.APIError as err:  # raised after the SDK's own retries
                self._fail("API_FAILURE", f"{type(err).__name__}: {err}", turn=turn, request=logged)
                return
            self._log("assistant", turn=turn, request=logged, response=response.to_dict(),
                      request_id=getattr(response, "_request_id", None),
                      stop_reason=response.stop_reason)
            if response.model != self.model:
                self._fail("API_FAILURE",
                           f"response.model {response.model!r} != configured {self.model!r}",
                           turn=turn)
                return
            if response.stop_reason == "refusal":
                details = getattr(response, "stop_details", None)
                self._fail("REFUSED", getattr(details, "category", None), turn=turn)
                return
            messages.append({"role": "assistant", "content": response.content})  # unchanged
            uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            if not uses:
                messages.append({"role": "user", "content": REMINDER})
                self._log("user", turn=turn, content=REMINDER, reminder=True)
                continue
            results = []
            for block in uses:
                if session.finished:
                    break
                r = session.call(block.name, block.input)
                content = json.dumps(r.result if r.ok else {"error": r.error}, sort_keys=True)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content,
                                "is_error": not r.ok})
            messages.append({"role": "user", "content": results})
            self._log("user", turn=turn, content=results)

    def _fail(self, outcome: Outcome, reason: str | None, **fields: Any) -> None:
        self.outcome, self.reason = outcome, reason
        self._log("end", outcome=outcome, reason=reason, **fields)
