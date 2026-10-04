"""Stdlib Kimi Code (OpenAI-compatible Chat Completions) adapter for configuration Y2."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
import urllib.error
import urllib.request
from typing import Any

from mirage.agents.base import LabSession
from mirage.agents.claude import REMINDER
from mirage.lab.tools import (
    MAX_TURNS,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
    prompt_sha256,
    render_observation,
)

API_URL = "https://api.kimi.com/coding/v1/chat/completions"
USER_AGENT = f"mirage-bio-cross-family/1.0 (python-urllib/{platform.python_version()})"
REQUEST_TIMEOUT_S = 300
RETRIES = 4


class KimiAPIError(RuntimeError):
    """A Kimi Chat Completions request failed after retry handling."""


class KimiChatClient:
    """Small injectable-client-compatible wrapper around urllib.

    Exposes ``responses.create`` so the experiment's metered wrapper can wrap either provider.
    """

    def __init__(self) -> None:
        self.responses = self

    def create(self, **params: Any) -> dict[str, Any]:
        api_key = os.environ.get("MOONSHOT_API_KEY", "").strip()
        if not api_key:
            raise KimiAPIError("MOONSHOT_API_KEY is not set")
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(params).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        for attempt in range(RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
                    try:
                        payload = json.loads(response.read().decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as err:
                        raise KimiAPIError("Kimi API returned invalid JSON") from err
                    if not isinstance(payload, dict):
                        raise KimiAPIError("Kimi API returned a non-object response")
                    return payload
            except urllib.error.HTTPError as err:
                if (err.code == 429 or 500 <= err.code <= 599) and attempt < RETRIES:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise KimiAPIError(f"HTTP {err.code} from Kimi API") from err
            except (urllib.error.URLError, TimeoutError) as err:
                if attempt < RETRIES:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise KimiAPIError(f"transport failure from Kimi API: {err}") from err
        raise KimiAPIError("Kimi API retries exhausted")


class KimiChatAgent:
    """MIRAGE lab agent using a pinned Kimi model through Chat Completions."""

    kind = "llm"
    name = "kimi_chat"

    def __init__(
        self,
        client: Any | None = None,
        *,
        model: str,
        effort: str,
        max_turns: int = MAX_TURNS,
    ) -> None:
        self._client = client
        self.model = model
        self.effort = effort
        self.max_turns = max_turns
        self.prompt_version = PROMPT_VERSION
        self.prompt_sha256 = prompt_sha256()
        self.sdk_version = f"urllib/{platform.python_version()}"
        self.outcome: str | None = None
        self.reason: str | None = None
        self.transcript: list[dict[str, Any]] = []
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": definition["name"],
                    "description": definition["description"],
                    "parameters": definition["input_schema"],
                },
            }
            for definition in TOOL_DEFINITIONS
        ]
        self.tools_sha256 = hashlib.sha256(
            json.dumps(self.tools, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _log(self, kind: str, **fields: Any) -> None:
        self.transcript.append({"kind": kind, **fields})

    def request_params(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *history],
            "tools": self.tools,
            "tool_choice": "auto",
            "reasoning_effort": self.effort,
            "max_tokens": 16_000,
        }

    def run(self, session: LabSession) -> None:
        client = self._client if self._client is not None else KimiChatClient()
        self.outcome, self.reason, self.transcript = None, None, []
        first = render_observation(session.observation())
        history: list[dict[str, Any]] = [{"role": "user", "content": first}]
        self._log("user", content=first)

        turn = 0
        while turn < self.max_turns and not session.finished:
            turn += 1
            params = self.request_params(history)
            logged = {k: v for k, v in params.items() if k not in {"messages", "tools"}}
            try:
                response = client.responses.create(**params)
            except KimiAPIError as err:
                self._fail("API_FAILURE", f"{type(err).__name__}: {err}", turn=turn, request=logged)
                return

            self._log("assistant", turn=turn, request=logged, response=response, response_id=response.get("id"))
            if response.get("model") != self.model:
                self._fail(
                    "API_FAILURE",
                    f"response.model {response.get('model')!r} != configured {self.model!r}",
                    turn=turn,
                )
                return
            choices = response.get("choices") or []
            if not choices or not isinstance(choices[0].get("message"), dict):
                self._fail("API_FAILURE", "response has no choices[0].message", turn=turn)
                return
            choice = choices[0]
            message = choice["message"]
            if choice.get("finish_reason") == "content_filter":
                self._fail("REFUSED", "finish_reason=content_filter", turn=turn)
                return
            # Kimi requires the complete assistant message (including reasoning_content) in history.
            history.append({k: v for k, v in message.items() if v is not None})

            calls = message.get("tool_calls") or []
            if not calls:
                self._append_reminder(history, turn)
                continue

            results = []
            for call in calls:
                function = call.get("function") or {}
                if session.finished:
                    value: Any = {"error": "episode already finished"}
                else:
                    arguments = self._arguments(function.get("arguments"))
                    result = session.call(function.get("name", ""), arguments)
                    value = result.result if result.ok else {"error": result.error}
                results.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": json.dumps(value, sort_keys=True),
                    }
                )
            history.extend(results)
            self._log("user", turn=turn, content=results)

    @staticmethod
    def _arguments(raw: Any) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _append_reminder(self, history: list[dict[str, Any]], turn: int) -> None:
        history.append({"role": "user", "content": REMINDER})
        self._log("user", turn=turn, content=REMINDER, reminder=True)

    def _fail(self, outcome: str, reason: str | None, **fields: Any) -> None:
        self.outcome, self.reason = outcome, reason
        self._log("end", outcome=outcome, reason=reason, **fields)
