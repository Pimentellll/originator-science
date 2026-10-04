"""Filesystem store for public episode records (privileged records live elsewhere)."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from mirage.provenance.events import EpisodeRecord
from mirage.provenance.validation import assert_valid_record

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_id(value: str) -> str:
    if not _SAFE_ID.fullmatch(value) or ".." in value:
        raise ValueError(f"unsafe identifier {value!r}")
    return value


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def record_to_jsonl(record: EpisodeRecord) -> str:
    """Line 1: header (record without events); then one line per event; then the terminal line."""
    header = record.model_dump(mode="json", exclude={"events", "terminal_decision"})
    lines = [json.dumps({"kind": "header", **header}, sort_keys=True)]
    lines += [
        json.dumps({"kind": "event", **e.model_dump(mode="json")}, sort_keys=True)
        for e in record.events
    ]
    terminal = (
        record.terminal_decision.model_dump(mode="json") if record.terminal_decision else None
    )
    lines.append(json.dumps({"kind": "terminal", "decision": terminal}, sort_keys=True))
    return "\n".join(lines) + "\n"


def record_from_jsonl(text: str) -> EpisodeRecord:
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not rows or rows[0].get("kind") != "header":
        raise ValueError("JSONL record must start with a header line")
    header = {k: v for k, v in rows[0].items() if k != "kind"}
    events, terminal = [], None
    for row in rows[1:]:
        kind = row.pop("kind", None)
        if kind == "event":
            events.append(row)
        elif kind == "terminal":
            terminal = row["decision"]
        else:
            raise ValueError(f"unknown JSONL line kind {kind!r}")
    return EpisodeRecord.model_validate({**header, "events": events, "terminal_decision": terminal})


class PublicRecordStore:
    """One ``<episode_id>.jsonl`` per episode: human-diffable and append-friendly."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, episode_id: str) -> Path:
        return self.root / f"{safe_id(episode_id)}.jsonl"

    def save(self, record: EpisodeRecord) -> Path:
        assert_valid_record(record)
        path = self._path(record.episode_id)
        atomic_write_text(path, record_to_jsonl(record))
        return path

    def exists(self, episode_id: str) -> bool:
        return self._path(episode_id).is_file()

    def load(self, episode_id: str) -> EpisodeRecord:
        path = self._path(episode_id)
        if not path.is_file():
            raise FileNotFoundError(episode_id)
        record = record_from_jsonl(path.read_text(encoding="utf-8"))
        assert_valid_record(record)
        return record

    def list_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.stem for p in self.root.glob("*.jsonl"))
