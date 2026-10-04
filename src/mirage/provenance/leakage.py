"""Trust-boundary scanner for public JSON (ADR 0007, TRUST_BOUNDARY.md).

Keys, not free text, are scanned: a hidden-truth channel is a structured field. Tests
additionally plant sentinel truth values and assert they never reach public payloads.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

# Key fragments that identify private simulator/evaluator state. Public assay outputs
# (log_kd, log_koff, p_assay_invalid, ...) deliberately do not match.
_FORBIDDEN_KEY = re.compile(
    r"(^_)"
    r"|(simulator_truth)|(privileged)|(hidden)|(ground_truth)|(latent)"
    r"|(^truth)|(_truth$)|(^true_)|(_true$)"
    r"|(particle)"
    r"|(^assay_valid)|(^model_valid)|(assay_validity)|(model_validity)"
    r"|(^failure_labels?$)|(^correct$)|(^justified$)|(evaluator)",
    re.IGNORECASE,
)


class TrustBoundaryViolation(ValueError):
    """Raised when a public payload carries a privileged field."""


def _walk(value: Any, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if _FORBIDDEN_KEY.search(str(key)):
                yield child_path, str(key)
            yield from _walk(child, child_path)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def find_privileged_fields(payload: Any) -> list[str]:
    """Paths of keys in a JSON-like payload that look privileged."""
    return [path for path, _ in _walk(payload, "")]


def assert_public_payload(payload: Any, *, where: str = "payload") -> None:
    found = find_privileged_fields(payload)
    if found:
        raise TrustBoundaryViolation(f"{where} contains privileged fields: {sorted(found)}")
