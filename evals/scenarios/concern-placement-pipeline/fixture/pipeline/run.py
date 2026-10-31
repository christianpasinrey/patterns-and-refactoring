import sys
from pathlib import Path

from pipeline.extract import read_orders
from pipeline.load import write_partition
from pipeline.transform import normalise


def main(day: str, source: Path, warehouse: Path) -> None:
    count = write_partition(normalise(read_orders(source)), day, warehouse)
    print(f"{day}: {count} rows")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
