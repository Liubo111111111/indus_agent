from __future__ import annotations

from collections.abc import Iterable, Iterator


def load_rows(records: Iterable[dict]) -> Iterator[dict]:
    for record in records:
        yield record

