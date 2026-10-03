"""VISIBLE agent protocols (DESIGN §4, §12). Frozen once merged."""

from __future__ import annotations

from typing import Any, Protocol

from mirage.lab.tools import Observation, ToolResponse


class LabSession(Protocol):
    """The only object an agent receives: no hidden state is reachable through it."""

    def observation(self) -> Observation: ...

    def call(self, tool: str, args: dict[str, Any]) -> ToolResponse: ...

    @property
    def finished(self) -> bool: ...


class Agent(Protocol):
    def run(self, session: LabSession) -> None: ...
