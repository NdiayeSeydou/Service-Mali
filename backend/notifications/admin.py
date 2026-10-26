from django.contrib import admin

from .models import NotificationAttempt, NotificationDelivery


class NotificationAttemptInline(admin.TabularInline):
    model = NotificationAttempt
    extra = 0
    can_delete = False
    readonly_fields = (
        "number",
        "status",
        "provider_message_id",
        "error",
        "started_at",
        "finished_at",
    )


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "recipient",
        "channel",
        "destination",
        "status",
        "attempts",
        "created_at",
        "sent_at",
    )
    list_filter = ("channel", "status", "event")
    search_fields = ("recipient__email", "destination", "event", "dedupe_key")
    readonly_fields = (
        "recipient",
        "channel",
        "event",
        "destination",
        "subject",
        "body",
        "dedupe_key",
        "attempts",
        "last_error",
        "provider_message_id",
        "created_at",
        "updated_at",
        "sent_at",
    )
    inlines = (NotificationAttemptInline,)
