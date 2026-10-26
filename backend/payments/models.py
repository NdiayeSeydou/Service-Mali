import uuid

from django.conf import settings
from django.db import models


class Payment(models.Model):
    class Provider(models.TextChoices):
        WAVE = "WAVE", "Wave"
        ORANGE_MONEY = "ORANGE_MONEY", "Orange Money"

    class Purpose(models.TextChoices):
        SERVICE = "SERVICE", "Prestation"
        SUBSCRIPTION = "SUBSCRIPTION", "Abonnement Premium"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        PAID = "PAID", "Payée"
        SETTLED = "SETTLED", "Fonds distribués"
        REFUNDED = "REFUNDED", "Remboursée"
        PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partiellement remboursée"
        FAILED = "FAILED", "Échouée"
        CANCELLED = "CANCELLED", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.SERVICE)
    request = models.ForeignKey(
        "requests.ServiceRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    quote = models.ForeignKey(
        "quotes.Quote", null=True, blank=True, on_delete=models.PROTECT, related_name="payments"
    )
    subscription = models.ForeignKey(
        "subscriptions.ProfessionalSubscription",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments"
    )
    amount_xof = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="XOF")
    provider_reference = models.CharField(max_length=120, blank=True)
    checkout_url = models.URLField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_reference"],
                condition=~models.Q(provider_reference=""),
                name="unique_provider_reference",
            )
        ]


class SandboxProviderSession(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SUCCEEDED = "SUCCEEDED", "Réussie"
        FAILED = "FAILED", "Échouée"
        REFUNDED = "REFUNDED", "Remboursée"

    payment = models.OneToOneField(
        Payment, on_delete=models.PROTECT, related_name="sandbox_session"
    )
    provider = models.CharField(max_length=20, choices=Payment.Provider.choices)
    reference = models.CharField(max_length=120, unique=True)
    amount_xof = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="XOF")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)


class WebhookEvent(models.Model):
    provider = models.CharField(max_length=20, choices=Payment.Provider.choices)
    event_id = models.CharField(max_length=160)
    payload_sha256 = models.CharField(max_length=64)
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"], name="unique_payment_webhook_event"
            )
        ]
        ordering = ["-received_at"]


class LedgerEntry(models.Model):
    class Account(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Client"
        PROVIDER = "PROVIDER", "Opérateur de paiement"
        ESCROW = "ESCROW", "Séquestre"
        PLATFORM = "PLATFORM", "Plateforme"
        PROFESSIONAL_PAYABLE = "PROFESSIONAL_PAYABLE", "Somme due au professionnel"

    class Type(models.TextChoices):
        ESCROW_CREDIT = "ESCROW_CREDIT", "Crédit du séquestre"
        COMMISSION = "COMMISSION", "Commission plateforme"
        PROFESSIONAL_RELEASE = "PROFESSIONAL_RELEASE", "Libération professionnel"
        CUSTOMER_REFUND = "CUSTOMER_REFUND", "Remboursement client"
        SUBSCRIPTION_PURCHASE = "SUBSCRIPTION_PURCHASE", "Abonnement Premium"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="ledger_entries")
    entry_type = models.CharField(max_length=32, choices=Type.choices)
    source_account = models.CharField(max_length=24, choices=Account.choices)
    destination_account = models.CharField(max_length=24, choices=Account.choices)
    amount_xof = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "entry_type"], name="unique_payment_ledger_entry_type"
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Le journal comptable est immuable.")
        if self.amount_xof <= 0:
            raise ValueError("Un mouvement comptable doit être strictement positif.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Le journal comptable est immuable.")


class PlatformConfiguration(models.Model):
    commission_basis_points = models.PositiveSmallIntegerField(
        default=1500, help_text="Base points; 1500 = 15 %."
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        config, _ = cls.objects.get_or_create(pk=1, defaults={"commission_basis_points": 1500})
        return config

    def save(self, *args, **kwargs):
        self.pk = 1
        if self.commission_basis_points > 10000:
            raise ValueError("La commission ne peut pas dépasser 100 %.")
        return super().save(*args, **kwargs)


class EscrowHold(models.Model):
    class Status(models.TextChoices):
        FROZEN = "FROZEN", "Gelé"
        RESOLVED = "RESOLVED", "Arbitré"

    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="escrow_hold")
    request = models.ForeignKey(
        "requests.ServiceRequest", on_delete=models.PROTECT, related_name="escrow_holds"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_escrow_holds"
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="resolved_escrow_holds",
    )
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.FROZEN)
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
