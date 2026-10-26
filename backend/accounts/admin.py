from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils import timezone

from .models import GalleryImage, ProfessionalProfile, ServiceArea, Trade, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (("Plateforme", {"fields": ("role", "phone")}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Plateforme", {"fields": ("email", "role", "phone")}),
    )
    list_display = ("email", "role", "is_active", "date_joined")
    list_filter = ("role", "is_active")
    search_fields = ("email", "username", "first_name", "last_name")


class GalleryInline(admin.TabularInline):
    model = GalleryImage
    extra = 0


@admin.register(ProfessionalProfile)
class ProfessionalProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "verification_status", "updated_at")
    list_filter = ("verification_status",)
    search_fields = ("user__email", "user__username")
    filter_horizontal = ("trades", "service_areas")
    inlines = (GalleryInline,)
    actions = ("verify_profiles", "reject_profiles")

    @admin.action(description="Valider les professionnels sélectionnés")
    def verify_profiles(self, request, queryset):
        queryset.update(
            verification_status=ProfessionalProfile.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
            verification_note="",
        )

    @admin.action(description="Refuser les professionnels sélectionnés")
    def reject_profiles(self, request, queryset):
        queryset.update(
            verification_status=ProfessionalProfile.VerificationStatus.REJECTED, verified_at=None
        )


admin.site.register((Trade, ServiceArea))
