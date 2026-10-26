from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.models import User
from requests_app.models import ServiceRequest, StateTransitionLog

from .models import Quote


@transaction.atomic
def accept_quote(quote_id, client):
    quote = Quote.objects.select_for_update().select_related("service_request").get(pk=quote_id)
    request = ServiceRequest.objects.select_for_update().get(pk=quote.service_request_id)
    if client.role != User.Role.CLIENT or request.client_id != client.pk:
        raise PermissionDenied("Seul le client propriétaire peut accepter un devis.")
    if request.status != ServiceRequest.Status.PUBLISHED:
        raise ValidationError("La demande n’accepte plus de devis.")
    other_quotes = list(
        Quote.objects.filter(service_request=request, status=Quote.Status.SENT).exclude(pk=quote.pk)
    )
    Quote.objects.filter(service_request=request).exclude(pk=quote.pk).update(
        status=Quote.Status.CLOSED
    )
    quote.status = Quote.Status.ACCEPTED
    quote.save(update_fields=["status"])
    old_status = request.status
    request.status = ServiceRequest.Status.QUOTE_ACCEPTED
    request.save(update_fields=["status", "updated_at"])
    StateTransitionLog.objects.create(
        request=request,
        actor=client,
        from_status=old_status,
        to_status=request.status,
        note=f"Devis {quote.pk} accepté",
    )
    from notifications.services import notify_user

    notify_user(
        quote.professional,
        event="QUOTE_ACCEPTED",
        subject="Votre devis a été accepté",
        body=f"Votre devis pour la demande {request.pk} a été accepté.",
        dedupe_key=f"quote:{quote.pk}:accepted:{quote.professional_id}",
    )
    notify_user(
        client,
        event="QUOTE_ACCEPTED_CONFIRMATION",
        subject="Devis accepté",
        body=f"Vous avez accepté un devis pour la demande {request.pk}.",
        dedupe_key=f"quote:{quote.pk}:accepted:{client.pk}",
    )
    for other in other_quotes:
        notify_user(
            other.professional,
            event="QUOTE_CLOSED",
            subject="La demande n’accepte plus de devis",
            body=f"Un autre devis a été choisi pour la demande {request.pk}.",
            dedupe_key=f"quote:{other.pk}:closed:{other.professional_id}",
        )
    return quote
