"""Stdlib OpenAI Responses API adapter for the cross-family experiment."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
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

API_URL = "https://api.openai.com/v1/responses"
REQUEST_TIMEOUT_S = 120
RETRIES = 4


class OpenAIAPIError(RuntimeError):
    """An OpenAI Responses API request failed after retry handling."""


class OpenAIResponsesClient:
    """Small injectable-client-compatible wrapper around urllib."""

    def __init__(self) -> None:
        self.responses = self

    def create(self, **params: Any) -> dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise OpenAIAPIError("OPENAI_API_KEY is not set")
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(params).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        for attempt in range(RETRIES + 1):
            try:
                with urllib.request.urlopen(
                    request, timeout=REQUEST_TIMEOUT_S
                ) as response:
                    try:
                        payload = json.loads(response.read().decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as err:
                        raise OpenAIAPIError(
                            "OpenAI Responses API returned invalid JSON"
                        ) from err
                    if not isinstance(payload, dict):
                        raise OpenAIAPIError(
                            "OpenAI Responses API returned a non-object response"
                        )
                    return payload
            except urllib.error.HTTPError as err:
                if self._retryable_status(err.code) and attempt < RETRIES:
                    time.sleep(2**attempt)
                    continue
                raise OpenAIAPIError(
                    f"HTTP {err.code} from OpenAI Responses API"
                ) from err
            except urllib.error.URLError as err:
                if attempt < RETRIES:
                    time.sleep(2**attempt)
                    continue
                raise OpenAIAPIError(
                    f"transport failure from OpenAI Responses API: {err.reason}"
                ) from err
        raise OpenAIAPIError("OpenAI Responses API retries exhausted")

    @staticmethod
    def _retryable_status(status: int) -> bool:
        return status == 429 or 500 <= status <= 599


class OpenAIResponsesAgent:
    """MIRAGE lab agent using a pinned model through the Responses API."""

    kind = "llm"
    name = "openai_responses"

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
                "name": definition["name"],
                "description": definition["description"],
                "parameters": definition["input_schema"],
                "strict": True,
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
            "instructions": SYSTEM_PROMPT,
            "input": history,
            "tools": self.tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "reasoning": {"effort": self.effort},
            "max_output_tokens": 16_000,
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }

    def run(self, session: LabSession) -> None:
        client = self._client if self._client is not None else OpenAIResponsesClient()
        self.outcome, self.reason, self.transcript = None, None, []
        first = render_observation(session.observation())
        history: list[dict[str, Any]] = [{"role": "user", "content": first}]
        self._log("user", content=first)

        turn = 0
        while turn < self.max_turns and not session.finished:
            turn += 1
            params = self.request_params(history)
            logged = {
                key: value
                for key, value in params.items()
                if key not in {"input", "instructions", "tools"}
            }
            try:
                response = client.responses.create(**params)
            except OpenAIAPIError as err:
                self._fail(
                    "API_FAILURE",
                    f"{type(err).__name__}: {err}",
                    turn=turn,
                    request=logged,
                )
                return

            response_id = response.get("id")
            self._log(
                "assistant",
                turn=turn,
                request=logged,
                response=response,
                response_id=response_id,
            )
            response_model = response.get("model")
            if not self._model_matches(response_model):
                self._fail(
                    "API_FAILURE",
                    f"response.model {response_model!r} != configured {self.model!r}",
                    turn=turn,
                )
                return

            output = response.get("output") or []
            history.extend(output)
            refusal = self._refusal(output)
            if refusal is not None:
                self._fail("REFUSED", refusal, turn=turn)
                return

            calls = [item for item in output if item.get("type") == "function_call"]
            if not calls:
                self._append_reminder(history, turn)
                continue

            results = []
            for call in calls:
                if session.finished:
                    break
                arguments = self._arguments(call.get("arguments"))
                result = session.call(call.get("name", ""), arguments)
                value = result.result if result.ok else {"error": result.error}
                tool_output = {
                    "type": "function_call_output",
                    "call_id": call.get("call_id"),
                    "output": json.dumps(value, sort_keys=True),
                }
                results.append(tool_output)
            history.extend(results)
            self._log("user", turn=turn, content=results)
            if response.get("status") == "incomplete" and not session.finished:
                self._append_reminder(history, turn)

    @staticmethod
    def _arguments(raw: Any) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _model_matches(self, response_model: Any) -> bool:
        if response_model == self.model:
            return True
        return isinstance(response_model, str) and re.fullmatch(
            rf"{re.escape(self.model)}-\d{{4}}-\d{{2}}-\d{{2}}",
            response_model,
        ) is not None

    @staticmethod
    def _refusal(output: list[dict[str, Any]]) -> str | None:
        for item in output:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    return str(content.get("refusal", ""))
        return None

    def _append_reminder(self, history: list[dict[str, Any]], turn: int) -> None:
        reminder = {"role": "user", "content": REMINDER}
        history.append(reminder)
        self._log("user", turn=turn, content=REMINDER, reminder=True)

    def _fail(self, outcome: str, reason: str | None, **fields: Any) -> None:
        self.outcome, self.reason = outcome, reason
        self._log("end", outcome=outcome, reason=reason, **fields)
