from django.contrib.auth.models import AbstractUser
from django.db import models

from .storage import PrivateIdentityStorage


class User(AbstractUser):
    class Role(models.TextChoices):
        CLIENT = "CLIENT", "Client"
        PROFESSIONAL = "PROFESSIONNEL", "Professionnel"
        ADMIN = "ADMIN", "Administrateur"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENT)
    phone = models.CharField(max_length=30, blank=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        should_be_staff = self.is_superuser or self.role == self.Role.ADMIN
        if self.is_staff != should_be_staff:
            self.is_staff = should_be_staff
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"is_staff"}
        super().save(*args, **kwargs)


class Trade(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ServiceArea(models.Model):
    name = models.CharField(max_length=120)
    city = models.CharField(max_length=120, default="Bamako")

    class Meta:
        unique_together = (("name", "city"),)

    def __str__(self):
        return f"{self.name}, {self.city}"


def identity_upload_to(instance, filename):
    return f"{instance.user_id}/{filename}"


class ProfessionalProfile(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "EN_ATTENTE", "En attente"
        VERIFIED = "VERIFIE", "Vérifié"
        REJECTED = "REFUSE", "Refusé"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="professional_profile")
    bio = models.TextField(blank=True)
    trades = models.ManyToManyField(Trade, blank=True, related_name="professionals")
    service_areas = models.ManyToManyField(ServiceArea, blank=True, related_name="professionals")
    identity_document = models.FileField(
        upload_to=identity_upload_to, storage=PrivateIdentityStorage(), blank=True
    )
    verification_status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )
    verification_note = models.TextField(blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_verified(self):
        return self.verification_status == self.VerificationStatus.VERIFIED


class GalleryImage(models.Model):
    profile = models.ForeignKey(
        ProfessionalProfile, on_delete=models.CASCADE, related_name="gallery"
    )
    image = models.ImageField(upload_to="professional-gallery/")
    caption = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
