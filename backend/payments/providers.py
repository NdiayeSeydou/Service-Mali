import hashlib
import hmac
import json
import secrets
import time
from abc import ABC, abstractmethod

from django.conf import settings

from .models import Payment, SandboxProviderSession


class ProviderError(Exception):
    pass


class InvalidWebhookSignature(ProviderError):
    pass


class PaymentProvider(ABC):
    code = None

    @abstractmethod
    def initier_paiement(self, payment, success_url, error_url): ...
    @abstractmethod
    def verifier_statut(self, reference): ...
    @abstractmethod
    def traiter_webhook(self, raw_body, signature): ...
    @abstractmethod
    def rembourser(self, payment, amount_xof): ...
    @abstractmethod
    def payer_professionnel(self, professional, amount_xof, reference): ...


class SandboxProvider(PaymentProvider):
    def _ensure_sandbox(self):
        if getattr(settings, "PAYMENT_MODE", "sandbox") != "sandbox":
            raise ProviderError(
                "Seul le mode sandbox est implémenté; aucun appel réel n’est effectué."
            )

    def initier_paiement(self, payment, success_url, error_url):
        self._ensure_sandbox()
        reference = f"{self.code.lower()}_{secrets.token_urlsafe(18)}"
        session = SandboxProviderSession.objects.create(
            payment=payment,
            provider=self.code,
            reference=reference,
            amount_xof=payment.amount_xof,
            currency=payment.currency,
        )
        payment.provider_reference = reference
        payment.checkout_url = f"http://localhost:8000/api/payments/sandbox/checkout/{reference}/"
        payment.save(update_fields=["provider_reference", "checkout_url"])
        return {"id": reference, "checkout_url": payment.checkout_url, "status": session.status}

    def verifier_statut(self, reference):
        self._ensure_sandbox()
        session = SandboxProviderSession.objects.select_related("payment").get(
            reference=reference, provider=self.code
        )
        return {
            "reference": reference,
            "status": session.status,
            "amount_xof": session.amount_xof,
            "currency": session.currency,
        }

    def traiter_webhook(self, raw_body, signature):
        self._ensure_sandbox()
        if not self.verifier_signature(raw_body, signature):
            raise InvalidWebhookSignature("Signature de webhook invalide.")
        try:
            payload = json.loads(raw_body)
            data = payload["data"]
            event_id = str(payload["id"])
            reference = str(data.get("id") or data.get("reference") or data.get("order_id"))
            amount = data.get("amount")
            currency = str(data.get("currency", "XOF")).upper()
            event_type = str(payload.get("type", ""))
        except (ValueError, TypeError, KeyError) as exc:
            raise ProviderError("Webhook incomplet ou JSON invalide.") from exc
        if not reference or reference == "None" or not event_id:
            raise ProviderError("Référence ou identifiant d’événement manquant.")
        return {
            "event_id": event_id,
            "reference": reference,
            "amount": amount,
            "currency": currency,
            "event_type": event_type,
        }

    def rembourser(self, payment, amount_xof):
        self._ensure_sandbox()
        if not 0 < amount_xof <= payment.amount_xof:
            raise ProviderError("Montant de remboursement invalide.")
        session = payment.sandbox_session
        session.status = (
            SandboxProviderSession.Status.REFUNDED
            if amount_xof == payment.amount_xof
            else SandboxProviderSession.Status.SUCCEEDED
        )
        session.save(update_fields=["status"])
        return {"status": "sandbox_refunded", "amount_xof": amount_xof}

    def payer_professionnel(self, professional, amount_xof, reference):
        self._ensure_sandbox()
        return {
            "status": "manual_pending",
            "professional_id": professional.pk,
            "amount_xof": amount_xof,
            "reference": reference,
        }

    @abstractmethod
    def verifier_signature(self, raw_body, signature): ...


class WaveProvider(SandboxProvider):
    code = Payment.Provider.WAVE
    secret_setting = "PAYMENT_WAVE_WEBHOOK_SECRET"

    def _secret(self):
        return getattr(settings, self.secret_setting, "")

    def sign_body(self, raw_body, timestamp=None):
        timestamp = str(int(timestamp if timestamp is not None else time.time()))
        body = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else str(raw_body)
        digest = hmac.new(
            self._secret().encode(), f"{timestamp}{body}".encode(), hashlib.sha256
        ).hexdigest()
        return f"t={timestamp},v1={digest}"

    def verifier_signature(self, raw_body, signature):
        if not signature or not self._secret():
            return False
        try:
            parts = [part.strip().split("=", 1) for part in signature.split(",")]
            timestamp = next(value for key, value in parts if key == "t")
            signatures = [value for key, value in parts if key == "v1"]
            sent_at = int(timestamp)
        except (ValueError, StopIteration):
            return False
        if sent_at < time.time() - 300 or sent_at > time.time() + 30:
            return False
        expected = self.sign_body(raw_body, sent_at).split("v1=", 1)[1]
        return any(hmac.compare_digest(expected, candidate) for candidate in signatures)


class OrangeMoneyProvider(SandboxProvider):
    code = Payment.Provider.ORANGE_MONEY
    secret_setting = "PAYMENT_ORANGE_WEBHOOK_SECRET"

    def obtenir_token(self):
        self._ensure_sandbox()
        return "sandbox-orange-money-token"

    def initier_paiement(self, payment, success_url, error_url):
        self.obtenir_token()
        return super().initier_paiement(payment, success_url, error_url)

    def sign_body(self, raw_body):
        body = raw_body if isinstance(raw_body, bytes) else str(raw_body).encode()
        return hmac.new(
            getattr(settings, self.secret_setting, "").encode(), body, hashlib.sha256
        ).hexdigest()

    def verifier_signature(self, raw_body, signature):
        secret = getattr(settings, self.secret_setting, "")
        return bool(
            secret and signature and hmac.compare_digest(self.sign_body(raw_body), signature)
        )


PROVIDERS = {
    Payment.Provider.WAVE: WaveProvider,
    Payment.Provider.ORANGE_MONEY: OrangeMoneyProvider,
}


def get_provider(provider_code):
    try:
        return PROVIDERS[provider_code]()
    except KeyError as exc:
        raise ProviderError("Opérateur de paiement non pris en charge.") from exc
