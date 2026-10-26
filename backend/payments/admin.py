from django.contrib import admin

from .models import (
    EscrowHold,
    LedgerEntry,
    Payment,
    PlatformConfiguration,
    SandboxProviderSession,
    WebhookEvent,
)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "purpose", "amount_xof", "currency", "status", "created_at")
    list_filter = ("provider", "purpose", "status")
    search_fields = ("provider_reference", "customer__email")
    readonly_fields = tuple(field.name for field in Payment._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "payment",
        "entry_type",
        "source_account",
        "destination_account",
        "amount_xof",
        "created_at",
    )
    list_filter = ("entry_type", "source_account", "destination_account")
    readonly_fields = tuple(field.name for field in LedgerEntry._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register((PlatformConfiguration, SandboxProviderSession, WebhookEvent))


@admin.register(EscrowHold)
class EscrowHoldAdmin(admin.ModelAdmin):
    list_display = (
        "request",
        "payment",
        "status",
        "created_by",
        "created_at",
        "released_by",
        "released_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("request__id", "payment__provider_reference", "reason")
    readonly_fields = (
        "payment",
        "request",
        "created_by",
        "released_by",
        "reason",
        "status",
        "created_at",
        "released_at",
    )
