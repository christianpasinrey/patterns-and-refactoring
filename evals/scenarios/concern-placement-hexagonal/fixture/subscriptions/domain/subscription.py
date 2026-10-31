from dataclasses import dataclass
from datetime import datetime


@dataclass
class Subscription:
    id: int
    owner_id: int
    plan: str
    cancelled_at: datetime | None = None

    def cancel(self, now: datetime) -> None:
        self.cancelled_at = now
