from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from subscriptions.adapters.django_repository import DjangoSubscriptions
from subscriptions.application.cancel import CancelSubscription


@login_required
@require_POST
def cancel(request, pk):
    CancelSubscription(DjangoSubscriptions())(pk, timezone.now())
    return JsonResponse({"cancelled": True})
