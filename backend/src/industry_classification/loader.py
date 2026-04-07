from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path


def load_rows(records: Iterable[dict]) -> Iterator[dict]:
    for record in records:
        yield record


def load_rows_from_file(path: str | Path, pt: str | None = None) -> Iterator[dict]:
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        lines = source.read_text(encoding="utf-8").splitlines()
        records = (json.loads(line) for line in lines if line.strip())
    else:
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("input_file_must_contain_a_json_array_or_jsonl_rows")
        records = iter(payload)

    for record in records:
        if pt is not None and str(record.get("pt", "")) != str(pt):
            continue
        if "pt" in record:
            record = {key: value for key, value in record.items() if key != "pt"}
        yield record
