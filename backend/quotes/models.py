from django.conf import settings
from django.db import models

from requests_app.models import ServiceRequest


class Quote(models.Model):
    class Status(models.TextChoices):
        SENT = "SENT", "Envoyé"
        ACCEPTED = "ACCEPTED", "Accepté"
        REJECTED = "REJECTED", "Refusé"
        CLOSED = "CLOSED", "Clôturé automatiquement"

    # request_id preserves the integer column created in the first scaffold migration.
    request_id = models.PositiveIntegerField(editable=False)
    service_request = models.ForeignKey(
        ServiceRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="quotes"
    )
    professional = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="quotes"
    )
    price_xof = models.PositiveBigIntegerField()
    estimated_days = models.PositiveSmallIntegerField()
    message = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SENT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.service_request_id:
            self.request_id = self.service_request_id
        return super().save(*args, **kwargs)
