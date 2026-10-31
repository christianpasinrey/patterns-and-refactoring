from typing import Protocol

from subscriptions.domain.subscription import Subscription


class Subscriptions(Protocol):
    def get(self, subscription_id: int) -> Subscription: ...

    def save(self, subscription: Subscription) -> None: ...
