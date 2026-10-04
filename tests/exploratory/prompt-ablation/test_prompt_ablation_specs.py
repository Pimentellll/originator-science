"""Specification checks for the registered prompt-ablation variants."""

from __future__ import annotations

import difflib
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

from mirage.lab.tools import SYSTEM_PROMPT, TOOL_DEFINITIONS, prompt_sha256

ROOT = Path(__file__).resolve().parents[3]
PROMPT_DIR = ROOT / "experiments" / "exploratory" / "prompt-ablation"
if str(PROMPT_DIR) not in sys.path:
    sys.path.insert(0, str(PROMPT_DIR))

from prompts import PROMPTS, variant_sha256


def _registration_text(heading: str) -> str:
    registration = (PROMPT_DIR / "REGISTRATION.md").read_text(encoding="utf-8")
    match = re.search(
        rf"## {heading} `[^`]+`.*?\n```\n(.*?)\n```",
        registration,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


def test_prompt_variants_match_registered_fenced_text_byte_for_byte() -> None:
    assert PROMPTS["prompt-v2-noceiling"] == _registration_text("3\\.1")
    assert PROMPTS["prompt-v2-minimal"] == _registration_text("3\\.2")
    assert all(not text.endswith("\n") for text in PROMPTS.values())


def test_noceiling_only_removes_the_two_registered_undiluted_words() -> None:
    source_words = SYSTEM_PROMPT.split()
    variant_words = PROMPTS["prompt-v2-noceiling"].split()
    differences = list(difflib.ndiff(source_words, variant_words))
    assert differences.count("- undiluted") == 2
    assert not [line for line in differences if line.startswith("+ ")]
    assert variant_words == [word for word in source_words if word != "undiluted"]


def test_variants_avoid_forbidden_cues_and_preserve_frozen_tools() -> None:
    forbidden = re.compile(r"saturat|ceiling|linear|undiluted|dilut", re.IGNORECASE)
    assert all(forbidden.search(text) is None for text in PROMPTS.values())
    assert TOOL_DEFINITIONS == __import__(
        "mirage.lab.tools", fromlist=["TOOL_DEFINITIONS"]
    ).TOOL_DEFINITIONS


def test_variant_hash_uses_variant_system_and_frozen_tools() -> None:
    system = PROMPTS["prompt-v2-noceiling"]
    expected = hashlib.sha256(
        json.dumps(
            {"system": system, "tools": TOOL_DEFINITIONS},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    assert variant_sha256(system) == expected
    assert variant_sha256(system) != prompt_sha256()


def test_driver_loads_from_its_path_with_importlib() -> None:
    driver_path = PROMPT_DIR / "driver.py"
    spec = importlib.util.spec_from_file_location(
        "prompt_ablation_driver_spec_test", driver_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module.PROMPTS is PROMPTS
