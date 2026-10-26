from django.conf import settings
from django.db import models
from django.utils import timezone


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=80, default="Premium mensuel", unique=True)
    price_xof = models.PositiveBigIntegerField(default=5000)
    duration_days = models.PositiveSmallIntegerField(default=30)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} — {self.price_xof} XOF"


class ProfessionalSubscription(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente de paiement"
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expirée"
        CANCELLED = "CANCELLED", "Annulée"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subscriptions"
    )
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_active(self):
        return (
            self.status == self.Status.ACTIVE
            and self.expires_at is not None
            and self.expires_at > timezone.now()
        )

    class Meta:
        ordering = ["-created_at"]
