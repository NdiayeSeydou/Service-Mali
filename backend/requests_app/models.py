from django.conf import settings
from django.db import models


class ServiceRequest(models.Model):
    class Status(models.TextChoices):
        PUBLISHED = "DEMANDE_PUBLIEE", "Demande publiée"
        QUOTE_ACCEPTED = "DEVIS_ACCEPTE", "Devis accepté"
        ESCROW_PAID = "PAYEE_SEQUESTRE", "Payée sous séquestre"
        IN_PROGRESS = "EN_COURS", "En cours"
        FINISHED_BY_PRO = "TERMINEE_PAR_PRO", "Terminée par le professionnel"
        VALIDATED_BY_CLIENT = "VALIDEE_PAR_CLIENT", "Validée par le client"
        FUNDS_RELEASED = "FONDS_LIBERES", "Fonds libérés"
        IN_DISPUTE = "EN_LITIGE", "En litige"
        RESOLVED = "RESOLUE", "Résolue"

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="service_requests"
    )
    category = models.CharField(max_length=120, blank=True)
    description = models.TextField()
    neighborhood = models.CharField(max_length=120, blank=True)
    budget_xof = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PUBLISHED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class StateTransitionLog(models.Model):
    request = models.ForeignKey(
        ServiceRequest, on_delete=models.PROTECT, related_name="state_history"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    from_status = models.CharField(max_length=32, choices=ServiceRequest.Status.choices)
    to_status = models.CharField(max_length=32, choices=ServiceRequest.Status.choices)
    note = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("L’historique des transitions est immuable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("L’historique des transitions est immuable.")
