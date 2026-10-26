from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("service_request", "client", "professional", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("client__email", "professional__email", "comment")
    readonly_fields = (
        "service_request",
        "client",
        "professional",
        "rating",
        "comment",
        "created_at",
    )
