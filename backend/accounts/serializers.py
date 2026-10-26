from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import GalleryImage, ProfessionalProfile, ServiceArea, Trade, User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    role = serializers.ChoiceField(choices=[User.Role.CLIENT, User.Role.PROFESSIONAL])

    class Meta:
        model = User
        fields = ("id", "email", "username", "password", "first_name", "last_name", "phone", "role")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if user.role == User.Role.PROFESSIONAL:
            ProfessionalProfile.objects.create(user=user)
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "username", "first_name", "last_name", "phone", "role")
        read_only_fields = ("id", "email", "role")


class GallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = GalleryImage
        fields = ("id", "image", "caption", "created_at")
        read_only_fields = ("id", "created_at")

    def validate_image(self, file):
        if file.size > 8 * 1024 * 1024:
            raise serializers.ValidationError("Image limitée à 8 Mo.")
        if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise serializers.ValidationError("Formats autorisés : JPEG, PNG ou WebP.")
        return file


class ProfessionalProfileSerializer(serializers.ModelSerializer):
    trades = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Trade.objects.filter(active=True), required=False
    )
    service_areas = serializers.PrimaryKeyRelatedField(
        many=True, queryset=ServiceArea.objects.all(), required=False
    )
    trade_details = serializers.StringRelatedField(source="trades", many=True, read_only=True)
    area_details = serializers.StringRelatedField(source="service_areas", many=True, read_only=True)
    gallery = GallerySerializer(many=True, read_only=True)
    user = UserSerializer(read_only=True)
    identity_document = serializers.FileField(write_only=True, required=False)

    class Meta:
        model = ProfessionalProfile
        fields = (
            "id",
            "user",
            "bio",
            "trades",
            "trade_details",
            "service_areas",
            "area_details",
            "gallery",
            "identity_document",
            "verification_status",
            "verification_note",
            "verified_at",
            "updated_at",
        )
        read_only_fields = ("verification_status", "verification_note", "verified_at", "updated_at")

    def validate_identity_document(self, file):
        if file.size > 8 * 1024 * 1024:
            raise serializers.ValidationError("Fichier limité à 8 Mo.")
        if file.content_type not in {"image/jpeg", "image/png", "application/pdf"}:
            raise serializers.ValidationError("Formats autorisés : JPEG, PNG ou PDF.")
        return file


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])


class LoginTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        return token
