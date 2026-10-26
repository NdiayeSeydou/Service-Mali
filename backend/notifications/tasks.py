import json
import re
import urllib.error
import urllib.request
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import NotificationAttempt, NotificationDelivery


def _send_email(delivery):
    sent = send_mail(
        delivery.subject or "Notification Services Mali",
        delivery.body,
        settings.DEFAULT_FROM_EMAIL,
        [delivery.destination],
        fail_silently=False,
    )
    if sent != 1:
        raise RuntimeError("Le backend e-mail n’a confirmé aucun envoi.")
    return ""


def _send_whatsapp(delivery):
    token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    if not token or not phone_number_id:
        raise RuntimeError(
            "WHATSAPP_ACCESS_TOKEN et WHATSAPP_PHONE_NUMBER_ID doivent être configurés."
        )
    recipient = re.sub(r"\D", "", delivery.destination)
    if not recipient:
        raise RuntimeError("Le numéro WhatsApp du destinataire est invalide.")
    version = getattr(settings, "WHATSAPP_API_VERSION", "v26.0")
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    template_name = getattr(settings, "WHATSAPP_TEMPLATE_NAME", "")
    if not template_name:
        raise RuntimeError("WHATSAPP_TEMPLATE_NAME doit désigner un modèle approuvé.")
    language = getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "fr")
    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": delivery.body[:1024]}]}
                ],
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"WhatsApp Cloud API HTTP {exc.code}: {detail}") from exc
    messages = result.get("messages", [])
    if not messages or not messages[0].get("id"):
        raise RuntimeError("WhatsApp Cloud API n’a pas confirmé l’identifiant du message.")
    return str(messages[0]["id"])


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
    name="notifications.deliver_notification",
)
def deliver_notification(self, delivery_id):
    with transaction.atomic():
        delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
        if delivery.status == NotificationDelivery.Status.SENT:
            return delivery.status
        if delivery.status == NotificationDelivery.Status.PROCESSING:
            stale_before = timezone.now() - timedelta(minutes=15)
            if delivery.updated_at >= stale_before:
                return delivery.status
            previous_attempt = (
                delivery.attempt_log.filter(status=NotificationAttempt.Status.PROCESSING)
                .order_by("-number")
                .first()
            )
            if previous_attempt:
                previous_attempt.status = NotificationAttempt.Status.FAILED
                previous_attempt.error = "Tentative interrompue après perte du worker."
                previous_attempt.finished_at = timezone.now()
                previous_attempt.save(update_fields=["status", "error", "finished_at"])
            if delivery.attempts >= 4:
                delivery.status = NotificationDelivery.Status.FAILED
                delivery.last_error = "Nombre maximal de tentatives atteint après perte du worker."
                delivery.save(update_fields=["status", "last_error", "updated_at"])
                return delivery.status
            delivery.status = NotificationDelivery.Status.QUEUED
        if delivery.attempts >= 4:
            delivery.status = NotificationDelivery.Status.FAILED
            delivery.last_error = "Nombre maximal de tentatives atteint."
            delivery.save(update_fields=["status", "last_error", "updated_at"])
            return delivery.status
        delivery.status = NotificationDelivery.Status.PROCESSING
        delivery.attempts += 1
        delivery.last_error = ""
        delivery.save(update_fields=["status", "attempts", "last_error", "updated_at"])
        attempt = NotificationAttempt.objects.create(
            delivery=delivery,
            number=delivery.attempts,
            status=NotificationAttempt.Status.PROCESSING,
        )
    try:
        provider_id = (
            _send_email(delivery)
            if delivery.channel == NotificationDelivery.Channel.EMAIL
            else _send_whatsapp(delivery)
        )
    except Exception as exc:
        now = timezone.now()
        retrying = self.request.retries < self.max_retries
        delivery.status = (
            NotificationDelivery.Status.QUEUED if retrying else NotificationDelivery.Status.FAILED
        )
        delivery.last_error = str(exc)[:4000]
        delivery.save(update_fields=["status", "last_error", "updated_at"])
        attempt.status = NotificationAttempt.Status.FAILED
        attempt.error = str(exc)[:4000]
        attempt.finished_at = now
        attempt.save(update_fields=["status", "error", "finished_at"])
        if retrying:
            raise self.retry(exc=exc, countdown=30 * (2**self.request.retries)) from exc
        return delivery.status
    now = timezone.now()
    delivery.status = NotificationDelivery.Status.SENT
    delivery.provider_message_id = provider_id
    delivery.sent_at = now
    delivery.last_error = ""
    delivery.save(
        update_fields=["status", "provider_message_id", "sent_at", "last_error", "updated_at"]
    )
    attempt.status = NotificationAttempt.Status.SENT
    attempt.provider_message_id = provider_id
    attempt.finished_at = now
    attempt.save(update_fields=["status", "provider_message_id", "finished_at"])
    return delivery.status


@shared_task(name="notifications.recover_queued_notifications")
def recover_queued_notifications():
    stale_before = timezone.now() - timedelta(minutes=15)
    candidate_ids = list(
        NotificationDelivery.objects.filter(
            Q(status=NotificationDelivery.Status.QUEUED)
            | Q(status=NotificationDelivery.Status.PROCESSING, updated_at__lt=stale_before),
            attempts__lt=4,
        )
        .order_by("created_at")
        .values_list("pk", flat=True)[:500]
    )
    NotificationDelivery.objects.filter(
        status=NotificationDelivery.Status.PROCESSING,
        updated_at__lt=stale_before,
        attempts__gte=4,
    ).update(
        status=NotificationDelivery.Status.FAILED,
        last_error="Nombre maximal de tentatives atteint après perte du worker.",
    )
    for delivery_id in candidate_ids:
        deliver_notification.delay(delivery_id)
    return len(candidate_ids)
