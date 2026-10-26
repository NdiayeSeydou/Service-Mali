from django.contrib import admin

from .models import ServiceRequest, StateTransitionLog


class StateTransitionInline(admin.TabularInline):
    model = StateTransitionLog
    extra = 0
    can_delete = False
    readonly_fields = ("actor", "from_status", "to_status", "note", "created_at")


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "category", "status", "created_at")
    list_filter = ("status", "category")
    search_fields = ("description", "client__email")
    readonly_fields = ("status", "created_at", "updated_at")
    inlines = (StateTransitionInline,)
