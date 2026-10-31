from django.conf import settings
from django.db import models


class Subscription(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan = models.CharField(max_length=40)
    cancelled_at = models.DateTimeField(null=True, blank=True)
