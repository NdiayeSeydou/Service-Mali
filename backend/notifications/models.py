from django.conf import settings
from django.db import models


class NotificationDelivery(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "E-mail"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "En attente"
        PROCESSING = "PROCESSING", "En cours"
        SENT = "SENT", "Envoyée"
        FAILED = "FAILED", "Échec"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="notification_deliveries"
    )
    channel = models.CharField(max_length=12, choices=Channel.choices)
    event = models.CharField(max_length=80)
    destination = models.CharField(max_length=254)
    subject = models.CharField(max_length=250, blank=True)
    body = models.TextField()
    dedupe_key = models.CharField(max_length=180, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    provider_message_id = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key", "channel"],
                condition=~models.Q(dedupe_key=""),
                name="unique_notification_channel_dedupe",
            )
        ]


class NotificationAttempt(models.Model):
    class Status(models.TextChoices):
        SENT = "SENT", "Envoyée"
        FAILED = "FAILED", "Échec"
        PROCESSING = "PROCESSING", "En cours"

    delivery = models.ForeignKey(
        NotificationDelivery, on_delete=models.PROTECT, related_name="attempt_log"
    )
    number = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices)
    provider_message_id = models.CharField(max_length=160, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["delivery", "number"], name="unique_notification_attempt_number"
            )
        ]
