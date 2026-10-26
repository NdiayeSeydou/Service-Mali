from django.db import transaction

from .models import NotificationDelivery


def notify_user(user, *, event, subject, body, dedupe_key):
    destinations = []
    if user.email:
        destinations.append((NotificationDelivery.Channel.EMAIL, user.email))
    if user.phone:
        destinations.append((NotificationDelivery.Channel.WHATSAPP, user.phone))
    deliveries = []
    for channel, destination in destinations:
        delivery, created = NotificationDelivery.objects.get_or_create(
            dedupe_key=f"{dedupe_key}:{channel}",
            channel=channel,
            defaults={
                "recipient": user,
                "event": event,
                "destination": destination,
                "subject": subject if channel == NotificationDelivery.Channel.EMAIL else "",
                "body": body,
            },
        )
        deliveries.append(delivery)
        if created:
            from .tasks import deliver_notification

            transaction.on_commit(lambda pk=delivery.pk: deliver_notification.delay(pk))
    return deliveries
