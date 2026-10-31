from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Subscription


@login_required
@require_POST
def cancel(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk)
    subscription.cancelled_at = timezone.now()
    subscription.save()
    return JsonResponse({"cancelled": True})
