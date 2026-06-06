"""Minimal JSONL checkpoint helpers.

Every phase appends one JSON line per processed sample immediately after
processing. On restart, the phase counts existing lines and skips that many
samples, resuming from where it left off.

The write is flushed + fsynced so the worst case on a crash is one duplicate
line for the last item, which callers de-duplicate on read by keying on idx.
"""
import json
import os
from pathlib import Path
from typing import Any


def count_lines(path: str) -> int:
    p = Path(path)
    if not p.exists():
        return 0
    with p.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def append_record(path: str, record: dict[str, Any]) -> None:
    os.makedirs(Path(path).parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_records(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    seen_idx: set[int] = set()
    records: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            idx = rec.get("idx")
            if idx in seen_idx:
                continue  # skip duplicates from crash mid-write
            seen_idx.add(idx)
            records.append(rec)
    return records
