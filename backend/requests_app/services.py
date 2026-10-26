from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.models import User

from .models import ServiceRequest, StateTransitionLog


class InvalidTransition(ValidationError):
    pass


@transaction.atomic
def transition_request(request_id, target, actor, *, note=""):
    request = ServiceRequest.objects.select_for_update().get(pk=request_id)
    current = request.status
    allowed = {
        ServiceRequest.Status.IN_PROGRESS: {ServiceRequest.Status.ESCROW_PAID},
        ServiceRequest.Status.FINISHED_BY_PRO: {ServiceRequest.Status.IN_PROGRESS},
        ServiceRequest.Status.VALIDATED_BY_CLIENT: {ServiceRequest.Status.FINISHED_BY_PRO},
        ServiceRequest.Status.IN_DISPUTE: {
            ServiceRequest.Status.ESCROW_PAID,
            ServiceRequest.Status.IN_PROGRESS,
            ServiceRequest.Status.FINISHED_BY_PRO,
        },
    }
    if target == ServiceRequest.Status.RESOLVED:
        raise InvalidTransition("Le litige doit être arbitré avec une décision financière.")
    if target == ServiceRequest.Status.ESCROW_PAID:
        raise InvalidTransition("Le séquestre ne peut être confirmé que par un webhook vérifié.")
    if target == ServiceRequest.Status.FUNDS_RELEASED:
        raise InvalidTransition("Les fonds ne peuvent être libérés que par la clôture du paiement.")
    if target not in allowed or current not in allowed[target]:
        raise InvalidTransition(f"Transition impossible : {current} → {target}.")
    if (
        target
        in {
            ServiceRequest.Status.IN_PROGRESS,
            ServiceRequest.Status.FINISHED_BY_PRO,
            ServiceRequest.Status.VALIDATED_BY_CLIENT,
        }
        and not request.payments.filter(status__in=["PAID", "SETTLED"]).exists()
    ):
        raise InvalidTransition("Une prestation doit avoir un paiement vérifié avant de continuer.")
    if target in {ServiceRequest.Status.IN_PROGRESS, ServiceRequest.Status.FINISHED_BY_PRO}:
        from quotes.models import Quote

        if not Quote.objects.filter(
            service_request=request,
            professional=actor,
            status=Quote.Status.ACCEPTED,
        ).exists():
            raise PermissionDenied("Seul le professionnel retenu peut modifier l’avancement.")
    elif target == ServiceRequest.Status.VALIDATED_BY_CLIENT:
        if actor != request.client:
            raise PermissionDenied("Seul le client propriétaire peut valider la prestation.")
        if not request.payments.filter(status="PAID").exists():
            raise InvalidTransition(
                "Une prestation doit avoir un paiement vérifié avant validation."
            )
    elif target == ServiceRequest.Status.IN_DISPUTE:
        from payments.models import EscrowHold, Payment
        from quotes.models import Quote

        payment = request.payments.filter(status=Payment.Status.PAID).first()
        if payment is None:
            raise InvalidTransition("Un litige ne peut geler qu’un séquestre payé.")
        if EscrowHold.objects.filter(payment=payment, status=EscrowHold.Status.FROZEN).exists():
            raise InvalidTransition("Le séquestre est déjà gelé pour un litige.")

        is_owner = (
            actor == request.client
            or Quote.objects.filter(
                service_request=request, professional=actor, status=Quote.Status.ACCEPTED
            ).exists()
        )
        if not is_owner:
            raise PermissionDenied(
                "Seuls les participants à la prestation peuvent ouvrir un litige."
            )
        if actor.role not in {User.Role.CLIENT, User.Role.PROFESSIONAL}:
            raise PermissionDenied("Rôle non autorisé.")
    request.status = target
    request.save(update_fields=["status", "updated_at"])
    StateTransitionLog.objects.create(
        request=request, actor=actor, from_status=current, to_status=target, note=note[:250]
    )
    if target == ServiceRequest.Status.IN_DISPUTE:
        from payments.models import EscrowHold, Payment
        from quotes.models import Quote

        payment = request.payments.get(status=Payment.Status.PAID)
        EscrowHold.objects.create(
            payment=payment,
            request=request,
            created_by=actor,
            reason=note[:1000],
        )
        professional = Quote.objects.get(
            service_request=request, status=Quote.Status.ACCEPTED
        ).professional
        from notifications.services import notify_user

        for recipient in {request.client, professional}:
            notify_user(
                recipient,
                event="DISPUTE_OPENED",
                subject="Un litige a été ouvert",
                body=f"Un litige a été ouvert pour la demande {request.pk}. Le séquestre est gelé pendant l’examen.",
                dedupe_key=f"dispute:{request.pk}:opened:{recipient.pk}",
            )
    if target == ServiceRequest.Status.VALIDATED_BY_CLIENT:
        from payments.services import release_funds_for_request

        release_funds_for_request(request.id, actor=actor)
    return request
