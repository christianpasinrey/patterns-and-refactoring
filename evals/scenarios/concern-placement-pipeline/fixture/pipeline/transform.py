from collections.abc import Iterable, Iterator


def normalise(rows: Iterable[dict]) -> Iterator[dict]:
    for row in rows:
        yield {"order_id": row["order_id"], "amount": float(row["amount"]), "currency": row["currency"].upper()}
