from subscriptions.adapters.models import SubscriptionRow
from subscriptions.domain.subscription import Subscription


class DjangoSubscriptions:
    def get(self, subscription_id: int) -> Subscription:
        row = SubscriptionRow.objects.get(pk=subscription_id)
        return Subscription(row.id, row.owner_id, row.plan, row.cancelled_at)

    def save(self, subscription: Subscription) -> None:
        SubscriptionRow.objects.filter(pk=subscription.id).update(cancelled_at=subscription.cancelled_at)
