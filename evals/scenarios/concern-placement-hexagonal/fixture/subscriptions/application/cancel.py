from datetime import datetime

from subscriptions.application.ports import Subscriptions


class CancelSubscription:
    def __init__(self, subscriptions: Subscriptions):
        self.subscriptions = subscriptions

    def __call__(self, subscription_id: int, now: datetime) -> None:
        subscription = self.subscriptions.get(subscription_id)
        subscription.cancel(now)
        self.subscriptions.save(subscription)
