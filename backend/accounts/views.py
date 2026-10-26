from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import generics, permissions, views
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import ProfessionalProfile, User
from .permissions import IsAdminRole
from .serializers import (
    GallerySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfessionalProfileSerializer,
    RegisterSerializer,
    UserSerializer,
)


class ResetThrottle(AnonRateThrottle):
    scope = "password_reset"


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfessionalProfileSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_object(self):
        if self.request.user.role != User.Role.PROFESSIONAL:
            raise permissions.PermissionDenied("Profil réservé aux professionnels.")
        profile, _ = ProfessionalProfile.objects.get_or_create(user=self.request.user)
        return profile


class GalleryCreateView(generics.CreateAPIView):
    serializer_class = GallerySerializer
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        profile = ProfessionalProfile.objects.get(user=self.request.user)
        serializer.save(profile=profile)


class PasswordResetRequestView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ResetThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = (
            get_user_model()
            .objects.filter(email__iexact=serializer.validated_data["email"], is_active=True)
            .first()
        )
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL}/reinitialiser-mot-de-passe?uid={uid}&token={token}"
            send_mail(
                "Réinitialisation de votre mot de passe",
                f"Pour choisir un nouveau mot de passe : {link}",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
        return Response(
            {"detail": "Si cette adresse existe, un e-mail de réinitialisation a été envoyé."}
        )


class PasswordResetConfirmView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = get_user_model().objects.get(
                pk=force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
            )
        except (ValueError, TypeError, OverflowError, get_user_model().DoesNotExist):
            return Response({"detail": "Lien invalide."}, status=400)
        if not default_token_generator.check_token(user, serializer.validated_data["token"]):
            return Response({"detail": "Lien invalide ou expiré."}, status=400)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Mot de passe mis à jour."})


class ProfessionalVerificationView(views.APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        try:
            profile = ProfessionalProfile.objects.get(pk=pk)
        except ProfessionalProfile.DoesNotExist:
            return Response(status=404)
        action = request.data.get("action")
        if action not in {"verify", "reject"}:
            return Response({"detail": "action doit être verify ou reject."}, status=400)
        profile.verification_status = (
            ProfessionalProfile.VerificationStatus.VERIFIED
            if action == "verify"
            else ProfessionalProfile.VerificationStatus.REJECTED
        )
        profile.verification_note = str(request.data.get("note", ""))[:2000]
        profile.verified_at = timezone.now() if action == "verify" else None
        profile.save(
            update_fields=["verification_status", "verification_note", "verified_at", "updated_at"]
        )
        return Response(ProfessionalProfileSerializer(profile).data)


class ProfessionalProfileListView(generics.ListAPIView):
    queryset = (
        ProfessionalProfile.objects.filter(
            verification_status=ProfessionalProfile.VerificationStatus.VERIFIED
        )
        .select_related("user")
        .prefetch_related("trades", "service_areas", "gallery")
    )
    serializer_class = ProfessionalProfileSerializer
    permission_classes = [permissions.AllowAny]
