"""Price variants of the frozen lab and Claude adapter (exploratory; no frozen file edited).

Only the price of one replicate reading changes; the budget stays at ``BUDGET_UNITS``.

* ``PricedLabEnvironment`` subclasses ``LabEnvironment`` and overrides only ``_measure``:
  it checks ``price * replicates`` against the remaining budget, delegates the actual
  measurement (latent model, noise streams, bookkeeping) to the frozen implementation, and
  then charges the extra ``(price - 1) * replicates`` units.
* ``PricedClaudeAgent`` subclasses ``ClaudeAgent`` and swaps only the three price strings in
  the system prompt, the ``measure_od`` tool description and the first observation. The
  frozen tool-use loop is reused as is.

At ``price = 1`` both are byte-identical to the frozen originals (see the tests).
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any
from unittest import mock

from pydantic import ValidationError

import mirage.agents.claude as claude_module
from mirage.agents.claude import ClaudeAgent
from mirage.lab.environment import LabEnvironment, _one_line
from mirage.lab.tools import (
    BUDGET_UNITS,
    MAX_TURNS,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
    MeasurementRequest,
    Observation,
    render_measurement,
    render_observation,
)

PRICES = (1, 3, 6)

# The exact frozen strings that state the price (src/mirage/lab/tools.py, prompt-v2).
_SYSTEM_PRICE = "costs 1 unit from a budget of 6 units"
_TOOL_PRICE = "and costs 1 budget unit."
_OBS_PRICE = '"cost": "1 unit per replicate reading"'


def _check_price(price: int) -> int:
    if type(price) is not int or not 1 <= price <= BUDGET_UNITS:
        raise ValueError(f"price must be an integer from 1 to {BUDGET_UNITS}, got {price!r}")
    return price


def _units(price: int) -> str:
    return "1 unit" if price == 1 else f"{price} units"


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"expected exactly one occurrence of {old!r} in the frozen text")
    return text.replace(old, new)


def priced_system_prompt(price: int) -> str:
    _check_price(price)
    return _replace_once(SYSTEM_PROMPT, _SYSTEM_PRICE,
                         f"costs {_units(price)} from a budget of {BUDGET_UNITS} units")


def priced_tool_definitions(price: int) -> list[dict[str, Any]]:
    _check_price(price)
    tools = copy.deepcopy(TOOL_DEFINITIONS)
    (measure,) = [t for t in tools if t["name"] == "measure_od"]
    unit = "1 budget unit" if price == 1 else f"{price} budget units"
    measure["description"] = _replace_once(measure["description"], _TOOL_PRICE,
                                           f"and costs {unit}.")
    return tools


def priced_render_observation(obs: Observation, price: int) -> str:
    _check_price(price)
    return _replace_once(render_observation(obs), _OBS_PRICE,
                         f'"cost": "{_units(price)} per replicate reading"')


def priced_prompt_sha256(price: int) -> str:
    """Same construction as ``mirage.lab.tools.prompt_sha256`` over the priced prompt."""
    payload = json.dumps(
        {"system": priced_system_prompt(price), "tools": priced_tool_definitions(price)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def priced_prompt_version(price: int) -> str:
    _check_price(price)
    return PROMPT_VERSION if price == 1 else f"{PROMPT_VERSION}+price{price}"


class PricedLabEnvironment(LabEnvironment):
    """``LabEnvironment`` in which one replicate reading costs ``price`` budget units."""

    def __init__(self, config, *, price: int, max_turns: int = MAX_TURNS) -> None:
        self.price = _check_price(price)
        super().__init__(config, max_turns=max_turns)

    def _measure(self, index: int, args: dict[str, Any]) -> tuple[dict | None, str | None]:
        try:
            req = MeasurementRequest(**args)
        except ValidationError as err:
            return None, _one_line(err)
        cost = self.price * req.replicates
        if self.price != 1 and cost > self.budget_remaining:
            return None, (
                f"replicates ({req.replicates}) at {self.price} units each ({cost} units) "
                f"exceeds remaining budget ({self.budget_remaining})"
            )
        # Frozen measurement path: same validation, latent value, noise stream and records.
        result, error = super()._measure(index, args)
        if error is not None or self.price == 1:
            return result, error
        self.budget_remaining -= cost - req.replicates  # the frozen path charged replicates
        priced = self.measurements[-1].model_copy(
            update={"cost_units": cost, "budget_remaining": self.budget_remaining}
        )
        self.measurements[-1] = priced
        return render_measurement(priced), None


class PricedClaudeAgent(ClaudeAgent):
    """``ClaudeAgent`` told that one replicate reading costs ``price`` units."""

    def __init__(self, client: Any | None = None, *, price: int, model: str,
                 max_turns: int = MAX_TURNS) -> None:
        super().__init__(client, model=model, max_turns=max_turns)
        self.price = _check_price(price)
        self.system_prompt = priced_system_prompt(price)
        self.tool_definitions = priced_tool_definitions(price)
        self.prompt_version = priced_prompt_version(price)
        self.prompt_sha256 = priced_prompt_sha256(price)

    def request_params(self, messages: list[Any]) -> dict[str, Any]:
        params = super().request_params(messages)
        params["system"] = self.system_prompt
        params["tools"] = self.tool_definitions
        return params

    def render_observation(self, obs: Observation) -> str:
        return priced_render_observation(obs, self.price)

    def run(self, session) -> None:
        # Reuse the frozen loop; only the module-level observation renderer it calls is
        # swapped for the duration of this call (single-threaded driver).
        with mock.patch.object(claude_module, "render_observation", self.render_observation):
            super().run(session)
