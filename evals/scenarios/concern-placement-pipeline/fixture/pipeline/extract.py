import csv
from collections.abc import Iterator
from pathlib import Path


def read_orders(path: Path) -> Iterator[dict]:
    with path.open(newline="") as source:
        yield from csv.DictReader(source)
