from django.contrib import admin

from .models import ProfessionalSubscription, SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price_xof", "duration_days", "active")
    list_filter = ("active",)


@admin.register(ProfessionalSubscription)
class ProfessionalSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "starts_at", "expires_at")
    list_filter = ("status",)
    search_fields = ("user__email",)
    readonly_fields = ("created_at",)
