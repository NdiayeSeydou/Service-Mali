import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from accounts.models import User
from notifications.models import NotificationAttempt, NotificationDelivery
from notifications.tasks import _send_whatsapp, deliver_notification

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "channel,provider",
    [
        ("EMAIL", "notifications.tasks._send_email"),
        ("WHATSAPP", "notifications.tasks._send_whatsapp"),
    ],
)
def test_celery_delivery_records_successful_attempt(channel, provider):
    recipient = User.objects.create_user(
        username=f"recipient-{channel.lower()}",
        email=f"{channel.lower()}@example.com",
        password="SecurePass!2026",
    )
    delivery = NotificationDelivery.objects.create(
        recipient=recipient,
        channel=channel,
        event="TEST",
        destination="+22370000000",
        subject="Essai",
        body="Notification testée",
    )
    with patch(provider, return_value="wamid.test-id") as send:
        result = deliver_notification.apply(args=(delivery.pk,), throw=True).get()

    delivery.refresh_from_db()
    attempt = delivery.attempt_log.get(number=1)
    assert result == NotificationDelivery.Status.SENT
    assert delivery.status == NotificationDelivery.Status.SENT
    assert delivery.attempts == 1
    assert delivery.provider_message_id == "wamid.test-id"
    assert attempt.status == NotificationAttempt.Status.SENT
    assert attempt.provider_message_id == "wamid.test-id"
    send.assert_called_once()


def test_failed_delivery_is_retried_and_each_attempt_is_logged():
    recipient = User.objects.create_user(
        username="failed-recipient", email="failed@example.com", password="SecurePass!2026"
    )
    delivery = NotificationDelivery.objects.create(
        recipient=recipient,
        channel=NotificationDelivery.Channel.EMAIL,
        event="TEST",
        destination=recipient.email,
        body="Échec simulé",
    )
    with patch("notifications.tasks._send_email", side_effect=RuntimeError("SMTP indisponible")):
        result = deliver_notification.apply(args=(delivery.pk,), throw=False).get()

    delivery.refresh_from_db()
    assert result == NotificationDelivery.Status.FAILED
    assert delivery.status == NotificationDelivery.Status.FAILED
    assert delivery.attempts == 4
    assert delivery.attempt_log.filter(status=NotificationAttempt.Status.FAILED).count() == 4
    assert "SMTP indisponible" in delivery.last_error


@override_settings(
    WHATSAPP_ACCESS_TOKEN="test-token",
    WHATSAPP_PHONE_NUMBER_ID="phone-id",
    WHATSAPP_API_VERSION="v26.0",
    WHATSAPP_TEMPLATE_NAME="service_notification",
    WHATSAPP_TEMPLATE_LANGUAGE="fr",
)
def test_whatsapp_cloud_api_uses_configured_template_and_logs_provider_id():
    recipient = User.objects.create_user(
        username="whatsapp-recipient",
        email="wa@example.com",
        phone="+223 70 00 00 00",
        password="SecurePass!2026",
    )
    delivery = NotificationDelivery.objects.create(
        recipient=recipient,
        channel=NotificationDelivery.Channel.WHATSAPP,
        event="TEST",
        destination=recipient.phone,
        body="Une variable de notification",
    )
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {"messages": [{"id": "wamid.cloud-1"}]}
    ).encode()
    with patch("notifications.tasks.urllib.request.urlopen", return_value=response) as send:
        provider_id = _send_whatsapp(delivery)
        request = send.call_args.args[0]
        payload = json.loads(request.data)

    assert provider_id == "wamid.cloud-1"
    assert request.full_url == "https://graph.facebook.com/v26.0/phone-id/messages"
    assert request.get_header("Authorization") == "Bearer test-token"
    assert payload["to"] == "22370000000"
    assert payload["template"]["name"] == "service_notification"
    assert payload["template"]["components"][0]["parameters"][0]["text"] == delivery.body


def test_notification_service_queues_email_and_whatsapp_once_per_event():
    from notifications.services import notify_user

    recipient = User.objects.create_user(
        username="both-channels",
        email="both@example.com",
        phone="+22370000000",
        password="SecurePass!2026",
    )
    first = notify_user(
        recipient,
        event="QUOTE",
        subject="Devis",
        body="Un devis est arrivé.",
        dedupe_key="quote:42:new",
    )
    second = notify_user(
        recipient,
        event="QUOTE",
        subject="Devis",
        body="Un devis est arrivé.",
        dedupe_key="quote:42:new",
    )

    assert {delivery.channel for delivery in first} == {"EMAIL", "WHATSAPP"}
    assert len(second) == 2
    assert NotificationDelivery.objects.filter(recipient=recipient).count() == 2
