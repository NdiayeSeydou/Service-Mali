import hashlib
import json
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import ProfessionalProfile, User
from quotes.models import Quote
from requests_app.models import ServiceRequest, StateTransitionLog
from subscriptions.models import ProfessionalSubscription

from .models import (
    EscrowHold,
    LedgerEntry,
    Payment,
    PlatformConfiguration,
    SandboxProviderSession,
    WebhookEvent,
)
from .providers import ProviderError, get_provider


class PaymentRejected(ValidationError):
    pass


def _whole_xof(value):
    try:
        decimal_amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PaymentRejected("Montant de paiement invalide.") from exc
    if (
        not decimal_amount.is_finite()
        or decimal_amount <= 0
        or decimal_amount != decimal_amount.to_integral_value()
    ):
        raise PaymentRejected("Le montant doit être un entier XOF strictement positif.")
    return int(decimal_amount)


@transaction.atomic
def create_service_checkout(client, request_id, provider_code, success_url, error_url):
    if client.role != User.Role.CLIENT:
        raise PermissionDenied("Seul le client peut payer une prestation.")
    service_request = ServiceRequest.objects.select_for_update().get(pk=request_id)
    if service_request.client_id != client.pk:
        raise PermissionDenied("Cette demande ne vous appartient pas.")
    if service_request.status != ServiceRequest.Status.QUOTE_ACCEPTED:
        raise PaymentRejected("Un devis doit être accepté avant le paiement.")
    quote = Quote.objects.get(service_request=service_request, status=Quote.Status.ACCEPTED)
    if service_request.payments.filter(
        status__in=[Payment.Status.PAID, Payment.Status.SETTLED]
    ).exists():
        raise PaymentRejected("Cette prestation a déjà été payée.")
    payment = Payment.objects.create(
        provider=provider_code,
        purpose=Payment.Purpose.SERVICE,
        request=service_request,
        quote=quote,
        customer=client,
        amount_xof=quote.price_xof,
    )
    try:
        get_provider(provider_code).initier_paiement(payment, success_url, error_url)
    except (ProviderError, ValueError) as exc:
        payment.delete()
        raise PaymentRejected(str(exc)) from exc
    return payment


@transaction.atomic
def create_subscription_checkout(user, plan, provider_code, success_url, error_url):
    if (
        user.role != User.Role.PROFESSIONAL
        or not ProfessionalProfile.objects.filter(
            user=user, verification_status=ProfessionalProfile.VerificationStatus.VERIFIED
        ).exists()
    ):
        raise PermissionDenied("Un compte professionnel vérifié est requis pour Premium.")
    subscription = ProfessionalSubscription.objects.create(user=user, plan=plan)
    payment = Payment.objects.create(
        provider=provider_code,
        purpose=Payment.Purpose.SUBSCRIPTION,
        subscription=subscription,
        customer=user,
        amount_xof=plan.price_xof,
    )
    try:
        get_provider(provider_code).initier_paiement(payment, success_url, error_url)
    except (ProviderError, ValueError) as exc:
        payment.delete()
        subscription.delete()
        raise PaymentRejected(str(exc)) from exc
    return payment


def _transition_paid_request(service_request, payment):
    if service_request.status != ServiceRequest.Status.QUOTE_ACCEPTED:
        raise PaymentRejected("La demande n’attend pas le paiement d’un devis accepté.")
    old_status = service_request.status
    service_request.status = ServiceRequest.Status.ESCROW_PAID
    service_request.save(update_fields=["status", "updated_at"])
    StateTransitionLog.objects.create(
        request=service_request,
        actor=None,
        from_status=old_status,
        to_status=service_request.status,
        note=f"Paiement {payment.pk} vérifié par le fournisseur",
    )


def _webhook_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PaymentRejected("Montant du webhook manquant ou invalide.") from exc
    if not amount.is_finite() or amount != amount.to_integral_value() or amount <= 0:
        raise PaymentRejected("Le montant du webhook doit être un entier XOF positif.")
    return int(amount)


@transaction.atomic
def process_payment_webhook(provider_code, raw_body, signature):
    provider = get_provider(provider_code)
    try:
        event = provider.traiter_webhook(raw_body, signature)
    except ProviderError as exc:
        raise PaymentRejected(str(exc)) from exc
    digest = hashlib.sha256(
        raw_body if isinstance(raw_body, bytes) else raw_body.encode()
    ).hexdigest()
    try:
        sandbox_session = (
            SandboxProviderSession.objects.select_for_update()
            .select_related("payment")
            .get(reference=event["reference"], provider=provider_code)
        )
    except SandboxProviderSession.DoesNotExist as exc:
        raise PaymentRejected("Session de paiement inconnue.") from exc
    payment = Payment.objects.select_for_update().get(pk=sandbox_session.payment_id)
    try:
        event_amount = _webhook_amount(event["amount"])
        verified = provider.verifier_statut(event["reference"])
        verified_amount = _webhook_amount(verified["amount_xof"])
    except (KeyError, ProviderError) as exc:
        raise PaymentRejected("Impossible de vérifier le paiement auprès de l’opérateur.") from exc
    if event["currency"] != "XOF" or verified.get("currency") != "XOF" or payment.currency != "XOF":
        raise PaymentRejected("Seuls les paiements XOF sont acceptés.")
    if event_amount != payment.amount_xof or verified_amount != payment.amount_xof:
        raise PaymentRejected(
            "Le montant confirmé par l’opérateur ne correspond pas au montant attendu."
        )
    if verified.get("status") != SandboxProviderSession.Status.SUCCEEDED:
        raise PaymentRejected("L’opérateur ne confirme pas la réussite de ce paiement.")
    webhook, created = WebhookEvent.objects.get_or_create(
        provider=provider_code, event_id=event["event_id"], defaults={"payload_sha256": digest}
    )
    if not created and webhook.processed:
        return {"status": "duplicate", "payment_id": str(payment.pk)}
    if payment.status in {Payment.Status.PAID, Payment.Status.SETTLED}:
        webhook.processed = True
        webhook.processed_at = timezone.now()
        webhook.save(update_fields=["processed", "processed_at"])
        return {"status": "duplicate", "payment_id": str(payment.pk)}
    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.save(update_fields=["status", "paid_at"])
    if payment.purpose == Payment.Purpose.SERVICE:
        _transition_paid_request(payment.request, payment)
        LedgerEntry.objects.create(
            payment=payment,
            entry_type=LedgerEntry.Type.ESCROW_CREDIT,
            source_account=LedgerEntry.Account.PROVIDER,
            destination_account=LedgerEntry.Account.ESCROW,
            amount_xof=payment.amount_xof,
        )
    else:
        _activate_subscription(payment)
        LedgerEntry.objects.create(
            payment=payment,
            entry_type=LedgerEntry.Type.SUBSCRIPTION_PURCHASE,
            source_account=LedgerEntry.Account.CUSTOMER,
            destination_account=LedgerEntry.Account.PLATFORM,
            amount_xof=payment.amount_xof,
        )
    webhook.processed = True
    webhook.processed_at = timezone.now()
    webhook.save(update_fields=["processed", "processed_at"])
    return {"status": "paid", "payment_id": str(payment.pk)}


def _activate_subscription(payment):
    subscription = payment.subscription
    now = timezone.now()
    previous = (
        ProfessionalSubscription.objects.filter(
            user=subscription.user,
            status=ProfessionalSubscription.Status.ACTIVE,
            expires_at__gt=now,
        )
        .order_by("-expires_at")
        .first()
    )
    starts_at = previous.expires_at if previous else now
    subscription.status = ProfessionalSubscription.Status.ACTIVE
    subscription.starts_at = starts_at
    subscription.expires_at = starts_at + timedelta(days=subscription.plan.duration_days)
    subscription.save(update_fields=["status", "starts_at", "expires_at"])


@transaction.atomic
def release_funds_for_request(request_id, *, actor):
    service_request = ServiceRequest.objects.select_for_update().get(pk=request_id)
    if service_request.payments.filter(escrow_hold__status=EscrowHold.Status.FROZEN).exists():
        raise PaymentRejected("Le séquestre est gelé pendant l’arbitrage du litige.")
    if service_request.status != ServiceRequest.Status.VALIDATED_BY_CLIENT:
        raise PaymentRejected("La prestation doit d’abord être validée par le client.")
    if actor != service_request.client:
        raise PermissionDenied("Seul le client propriétaire peut valider la prestation.")
    payment = (
        service_request.payments.select_for_update()
        .filter(status=Payment.Status.PAID)
        .order_by("-created_at")
        .first()
    )
    if payment is None:
        raise PaymentRejected("Aucun paiement vérifié à libérer.")
    configuration = PlatformConfiguration.current()
    commission = payment.amount_xof * configuration.commission_basis_points // 10000
    professional_amount = payment.amount_xof - commission
    if commission:
        LedgerEntry.objects.create(
            payment=payment,
            entry_type=LedgerEntry.Type.COMMISSION,
            source_account=LedgerEntry.Account.ESCROW,
            destination_account=LedgerEntry.Account.PLATFORM,
            amount_xof=commission,
        )
    LedgerEntry.objects.create(
        payment=payment,
        entry_type=LedgerEntry.Type.PROFESSIONAL_RELEASE,
        source_account=LedgerEntry.Account.ESCROW,
        destination_account=LedgerEntry.Account.PROFESSIONAL_PAYABLE,
        amount_xof=professional_amount,
    )
    old_status = service_request.status
    service_request.status = ServiceRequest.Status.FUNDS_RELEASED
    service_request.save(update_fields=["status", "updated_at"])
    StateTransitionLog.objects.create(
        request=service_request,
        actor=actor,
        from_status=old_status,
        to_status=service_request.status,
        note=f"Libération; commission {commission} XOF",
    )
    payment.status = Payment.Status.SETTLED
    payment.settled_at = timezone.now()
    payment.save(update_fields=["status", "settled_at"])
    get_provider(payment.provider).payer_professionnel(
        payment.quote.professional, professional_amount, str(payment.pk)
    )
    return {
        "gross_xof": payment.amount_xof,
        "commission_xof": commission,
        "professional_xof": professional_amount,
    }


def sandbox_confirm_payment(reference):
    session = SandboxProviderSession.objects.select_related("payment").get(reference=reference)
    if session.status != SandboxProviderSession.Status.PENDING:
        raise PaymentRejected("Cette session sandbox n’est plus en attente.")
    session.status = SandboxProviderSession.Status.SUCCEEDED
    session.save(update_fields=["status"])
    event = json.dumps(
        {
            "id": f"sandbox_{secrets.token_hex(12)}",
            "type": "payment.succeeded",
            "data": {
                "id": reference,
                "amount": str(session.amount_xof),
                "currency": session.currency,
            },
        },
        separators=(",", ":"),
    ).encode()
    provider = get_provider(session.provider)
    signature = provider.sign_body(event)
    return process_payment_webhook(session.provider, event, signature)
