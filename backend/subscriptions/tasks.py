from celery import shared_task
from django.utils import timezone

from .models import ProfessionalSubscription


@shared_task
def expire_subscriptions():
    return ProfessionalSubscription.objects.filter(
        status=ProfessionalSubscription.Status.ACTIVE, expires_at__lte=timezone.now()
    ).update(status=ProfessionalSubscription.Status.EXPIRED)
