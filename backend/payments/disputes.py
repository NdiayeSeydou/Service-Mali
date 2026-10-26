from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from requests_app.models import ServiceRequest, StateTransitionLog

from .models import EscrowHold, LedgerEntry, Payment, PlatformConfiguration
from .providers import get_provider
from .services import PaymentRejected


class InvalidDisputeOutcome(ValidationError):
    pass


@transaction.atomic
def resolve_dispute(request_id, *, actor, outcome, professional_gross_xof=None):
    service_request = ServiceRequest.objects.select_for_update().get(pk=request_id)
    if actor.role != User.Role.ADMIN:
        raise PermissionDenied("Seul un administrateur peut arbitrer un litige.")
    if service_request.status != ServiceRequest.Status.IN_DISPUTE:
        raise InvalidDisputeOutcome("La demande n’est pas en litige.")
    payment = (
        service_request.payments.select_for_update().filter(status=Payment.Status.PAID).first()
    )
    if payment is None:
        raise PaymentRejected("Aucun séquestre vérifié à arbitrer.")
    hold = (
        EscrowHold.objects.select_for_update()
        .filter(payment=payment, status=EscrowHold.Status.FROZEN)
        .first()
    )
    if hold is None:
        raise PaymentRejected("Le séquestre n’est pas gelé par un litige actif.")
    if outcome == "RELEASE":
        professional_gross = payment.amount_xof
    elif outcome == "REFUND":
        professional_gross = 0
    elif outcome == "SPLIT":
        if (
            isinstance(professional_gross_xof, bool)
            or not isinstance(professional_gross_xof, int)
            or not 0 < professional_gross_xof < payment.amount_xof
        ):
            raise InvalidDisputeOutcome(
                "Le partage doit attribuer au professionnel un entier XOF entre 1 et le montant total moins 1."
            )
        professional_gross = professional_gross_xof
    else:
        raise InvalidDisputeOutcome("Décision attendue : RELEASE, REFUND ou SPLIT.")
    refund_amount = payment.amount_xof - professional_gross
    commission = (
        professional_gross * PlatformConfiguration.current().commission_basis_points // 10000
    )
    professional_net = professional_gross - commission
    provider = get_provider(payment.provider)
    if refund_amount:
        provider.rembourser(payment, refund_amount)
        LedgerEntry.objects.create(
            payment=payment,
            entry_type=LedgerEntry.Type.CUSTOMER_REFUND,
            source_account=LedgerEntry.Account.ESCROW,
            destination_account=LedgerEntry.Account.CUSTOMER,
            amount_xof=refund_amount,
        )
    if commission:
        LedgerEntry.objects.create(
            payment=payment,
            entry_type=LedgerEntry.Type.COMMISSION,
            source_account=LedgerEntry.Account.ESCROW,
            destination_account=LedgerEntry.Account.PLATFORM,
            amount_xof=commission,
        )
    if professional_net:
        LedgerEntry.objects.create(
            payment=payment,
            entry_type=LedgerEntry.Type.PROFESSIONAL_RELEASE,
            source_account=LedgerEntry.Account.ESCROW,
            destination_account=LedgerEntry.Account.PROFESSIONAL_PAYABLE,
            amount_xof=professional_net,
        )
        provider.payer_professionnel(payment.quote.professional, professional_net, str(payment.pk))
    payment.status = (
        Payment.Status.REFUNDED
        if refund_amount == payment.amount_xof
        else Payment.Status.PARTIALLY_REFUNDED
        if refund_amount
        else Payment.Status.SETTLED
    )
    payment.settled_at = timezone.now()
    payment.save(update_fields=["status", "settled_at"])
    hold.status = EscrowHold.Status.RESOLVED
    hold.released_by = actor
    hold.released_at = timezone.now()
    hold.save(update_fields=["status", "released_by", "released_at"])
    old_status = service_request.status
    service_request.status = ServiceRequest.Status.RESOLVED
    service_request.save(update_fields=["status", "updated_at"])
    StateTransitionLog.objects.create(
        request=service_request,
        actor=actor,
        from_status=old_status,
        to_status=service_request.status,
        note=f"Arbitrage {outcome}; remboursement {refund_amount} XOF",
    )
    from notifications.services import notify_user
    from quotes.models import Quote

    professional = Quote.objects.get(
        service_request=service_request, status=Quote.Status.ACCEPTED
    ).professional
    for recipient in {service_request.client, professional}:
        notify_user(
            recipient,
            event="DISPUTE_RESOLVED",
            subject="Le litige a été arbitré",
            body=f"Le litige de la demande {service_request.pk} a été arbitré. Issue : {outcome}.",
            dedupe_key=f"dispute:{service_request.pk}:resolved:{recipient.pk}",
        )
    return {
        "outcome": outcome,
        "refund_xof": refund_amount,
        "commission_xof": commission,
        "professional_xof": professional_net,
    }
