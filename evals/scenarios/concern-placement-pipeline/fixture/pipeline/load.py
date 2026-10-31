import json
from collections.abc import Iterable
from pathlib import Path


def write_partition(rows: Iterable[dict], day: str, warehouse: Path) -> int:
    target = warehouse / f"orders/day={day}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w") as sink:
        for row in rows:
            sink.write(json.dumps(row) + "\n")
            count += 1
    return count
