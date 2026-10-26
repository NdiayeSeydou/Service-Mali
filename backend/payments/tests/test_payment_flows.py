import json
import time

import pytest
from django.test import override_settings

from accounts.models import ProfessionalProfile, User
from payments.disputes import resolve_dispute
from payments.models import (
    EscrowHold,
    LedgerEntry,
    Payment,
    PlatformConfiguration,
    SandboxProviderSession,
)
from payments.providers import OrangeMoneyProvider, WaveProvider
from payments.services import (
    PaymentRejected,
    process_payment_webhook,
    release_funds_for_request,
)
from quotes.models import Quote
from requests_app.models import ServiceRequest
from requests_app.services import InvalidTransition, transition_request

pytestmark = pytest.mark.django_db


@pytest.fixture
def payment_case():
    client = User.objects.create_user(
        username="payer", email="payer@example.com", password="SecurePass!2026"
    )
    pro = User.objects.create_user(
        username="artisan",
        email="artisan@example.com",
        password="SecurePass!2026",
        role=User.Role.PROFESSIONAL,
    )
    ProfessionalProfile.objects.create(
        user=pro, verification_status=ProfessionalProfile.VerificationStatus.VERIFIED
    )
    request = ServiceRequest.objects.create(
        client=client,
        category="Plomberie",
        description="Réparer une fuite",
        status=ServiceRequest.Status.QUOTE_ACCEPTED,
    )
    quote = Quote.objects.create(
        service_request=request,
        professional=pro,
        price_xof=10000,
        estimated_days=2,
        status=Quote.Status.ACCEPTED,
    )
    payment = Payment.objects.create(
        provider=Payment.Provider.WAVE,
        request=request,
        quote=quote,
        customer=client,
        amount_xof=10000,
        provider_reference="wave_test_session",
    )
    session = SandboxProviderSession.objects.create(
        payment=payment,
        provider=Payment.Provider.WAVE,
        reference=payment.provider_reference,
        amount_xof=payment.amount_xof,
        status=SandboxProviderSession.Status.SUCCEEDED,
    )
    return {
        "client": client,
        "professional": pro,
        "request": request,
        "quote": quote,
        "payment": payment,
        "session": session,
    }


def webhook_body(reference, *, amount="10000", event_id="evt-1"):
    return json.dumps(
        {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "id": reference,
                "amount": amount,
                "currency": "XOF",
                "payment_status": "succeeded",
            },
        },
        separators=(",", ":"),
    ).encode()


def test_webhook_replayed_twice_is_idempotent(payment_case):
    body = webhook_body(payment_case["payment"].provider_reference)
    signature = WaveProvider().sign_body(body)
    first = process_payment_webhook(Payment.Provider.WAVE, body, signature)
    second = process_payment_webhook(Payment.Provider.WAVE, body, signature)
    payment_case["payment"].refresh_from_db()
    assert first["status"] == "paid"
    assert second["status"] == "duplicate"
    assert payment_case["payment"].status == Payment.Status.PAID
    assert LedgerEntry.objects.filter(payment=payment_case["payment"]).count() == 1


def test_invalid_signature_does_not_mark_payment_paid(payment_case):
    body = webhook_body(payment_case["payment"].provider_reference)
    with pytest.raises(PaymentRejected, match="Signature"):
        process_payment_webhook(Payment.Provider.WAVE, body, "t=1,v1=bad")
    payment_case["payment"].refresh_from_db()
    assert payment_case["payment"].status == Payment.Status.PENDING
    assert not LedgerEntry.objects.filter(payment=payment_case["payment"]).exists()


def test_webhook_amount_mismatch_is_rejected(payment_case):
    body = webhook_body(payment_case["payment"].provider_reference, amount="9999")
    with pytest.raises(PaymentRejected, match="montant"):
        process_payment_webhook(Payment.Provider.WAVE, body, WaveProvider().sign_body(body))
    payment_case["payment"].refresh_from_db()
    assert payment_case["payment"].status == Payment.Status.PENDING
    assert not LedgerEntry.objects.filter(payment=payment_case["payment"]).exists()


def test_client_cannot_validate_service_without_verified_payment(payment_case):
    request = payment_case["request"]
    request.status = ServiceRequest.Status.FINISHED_BY_PRO
    request.save(update_fields=["status"])
    with pytest.raises(InvalidTransition, match="paiement vérifié"):
        transition_request(
            request.pk, ServiceRequest.Status.VALIDATED_BY_CLIENT, payment_case["client"]
        )
    request.refresh_from_db()
    assert request.status == ServiceRequest.Status.FINISHED_BY_PRO


@override_settings(PAYMENT_MODE="sandbox")
def test_funds_release_twice_does_not_duplicate_ledger(payment_case):
    payment = payment_case["payment"]
    payment.status = Payment.Status.PAID
    payment.save(update_fields=["status"])
    request = payment_case["request"]
    request.status = ServiceRequest.Status.FINISHED_BY_PRO
    request.save(update_fields=["status"])
    LedgerEntry.objects.create(
        payment=payment,
        entry_type=LedgerEntry.Type.ESCROW_CREDIT,
        source_account=LedgerEntry.Account.PROVIDER,
        destination_account=LedgerEntry.Account.ESCROW,
        amount_xof=payment.amount_xof,
    )
    PlatformConfiguration.objects.create(pk=1, commission_basis_points=1500)
    transition_request(
        request.pk, ServiceRequest.Status.VALIDATED_BY_CLIENT, payment_case["client"]
    )
    with pytest.raises(PaymentRejected, match="validée"):
        release_funds_for_request(request.pk, actor=payment_case["client"])
    payment.refresh_from_db()
    request.refresh_from_db()
    entries = LedgerEntry.objects.filter(payment=payment)
    assert request.status == ServiceRequest.Status.FUNDS_RELEASED
    assert payment.status == Payment.Status.SETTLED
    assert entries.count() == 3
    credits = sum(
        entry.amount_xof
        for entry in entries
        if entry.destination_account == LedgerEntry.Account.ESCROW
    )
    debits = sum(
        entry.amount_xof for entry in entries if entry.source_account == LedgerEntry.Account.ESCROW
    )
    assert credits == debits == payment.amount_xof
    assert entries.get(entry_type=LedgerEntry.Type.COMMISSION).amount_xof == 1500
    assert entries.get(entry_type=LedgerEntry.Type.PROFESSIONAL_RELEASE).amount_xof == 8500


def test_wave_signature_uses_timestamp_and_raw_body():
    provider = WaveProvider()
    body = b'{"id":"evt"}'
    signature = provider.sign_body(body, timestamp=int(time.time()))
    with override_settings(PAYMENT_WAVE_WEBHOOK_SECRET="sandbox-wave-webhook-secret"):
        assert WaveProvider().verifier_signature(body, signature)
        assert not WaveProvider().verifier_signature(body, signature.replace("v1=", "v1=bad"))


def test_orange_money_sandbox_signature():
    provider = OrangeMoneyProvider()
    body = b'{"id":"evt"}'
    with override_settings(PAYMENT_ORANGE_WEBHOOK_SECRET="sandbox-orange-webhook-secret"):
        signature = provider.sign_body(body)
        assert OrangeMoneyProvider().verifier_signature(body, signature)
        assert not OrangeMoneyProvider().verifier_signature(body, "invalid")


def test_provider_status_amount_mismatch_is_rejected(payment_case):
    session = payment_case["session"]
    session.amount_xof = 9000
    session.save(update_fields=["amount_xof"])
    body = webhook_body(payment_case["payment"].provider_reference)
    with pytest.raises(PaymentRejected, match="montant"):
        process_payment_webhook(Payment.Provider.WAVE, body, WaveProvider().sign_body(body))
    payment_case["payment"].refresh_from_db()
    assert payment_case["payment"].status == Payment.Status.PENDING
    assert not LedgerEntry.objects.filter(payment=payment_case["payment"]).exists()


@override_settings(PAYMENT_MODE="sandbox")
def test_dispute_freezes_escrow_until_admin_arbitrates(payment_case):
    payment = payment_case["payment"]
    payment.status = Payment.Status.PAID
    payment.save(update_fields=["status"])
    request = payment_case["request"]
    request.status = ServiceRequest.Status.ESCROW_PAID
    request.save(update_fields=["status"])
    LedgerEntry.objects.create(
        payment=payment,
        entry_type=LedgerEntry.Type.ESCROW_CREDIT,
        source_account=LedgerEntry.Account.PROVIDER,
        destination_account=LedgerEntry.Account.ESCROW,
        amount_xof=payment.amount_xof,
    )

    transition_request(
        request.pk,
        ServiceRequest.Status.IN_DISPUTE,
        payment_case["client"],
        note="Travail incomplet",
    )

    hold = EscrowHold.objects.get(payment=payment)
    assert hold.status == EscrowHold.Status.FROZEN
    assert payment_case["request"].payments.get().status == Payment.Status.PAID
    assert LedgerEntry.objects.filter(payment=payment).count() == 1
    with pytest.raises(PaymentRejected, match="gelé"):
        release_funds_for_request(request.pk, actor=payment_case["client"])
    with pytest.raises(InvalidTransition, match="arbitré"):
        transition_request(request.pk, ServiceRequest.Status.RESOLVED, payment_case["client"])

    admin = User.objects.create_user(
        username="arbitrator",
        email="arbitrator@example.com",
        password="SecurePass!2026",
        role=User.Role.ADMIN,
    )
    result = resolve_dispute(request.pk, actor=admin, outcome="SPLIT", professional_gross_xof=5000)

    hold.refresh_from_db()
    payment.refresh_from_db()
    request.refresh_from_db()
    assert result == {
        "outcome": "SPLIT",
        "refund_xof": 5000,
        "commission_xof": 750,
        "professional_xof": 4250,
    }
    assert hold.status == EscrowHold.Status.RESOLVED
    assert hold.released_by == admin
    assert payment.status == Payment.Status.PARTIALLY_REFUNDED
    assert request.status == ServiceRequest.Status.RESOLVED
    assert LedgerEntry.objects.filter(payment=payment).count() == 4
