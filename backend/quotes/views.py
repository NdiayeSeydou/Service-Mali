from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers, views
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounts.models import ProfessionalProfile, User
from requests_app.models import ServiceRequest

from .models import Quote
from .services import accept_quote


class QuoteSerializer(serializers.ModelSerializer):
    request_id = serializers.PrimaryKeyRelatedField(
        source="service_request", queryset=ServiceRequest.objects.all()
    )

    class Meta:
        model = Quote
        fields = (
            "id",
            "request_id",
            "professional",
            "price_xof",
            "estimated_days",
            "message",
            "status",
            "created_at",
        )
        read_only_fields = ("id", "professional", "status", "created_at")


class QuoteCreateView(generics.CreateAPIView):
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user
        if user.role != User.Role.PROFESSIONAL:
            raise PermissionDenied("Seuls les professionnels peuvent envoyer un devis.")
        if not ProfessionalProfile.objects.filter(
            user=user, verification_status=ProfessionalProfile.VerificationStatus.VERIFIED
        ).exists():
            raise PermissionDenied(
                "Votre compte professionnel doit être vérifié pour envoyer un devis."
            )
        service_request = serializer.validated_data["service_request"]
        if service_request.status != ServiceRequest.Status.PUBLISHED:
            raise PermissionDenied("Cette demande n’accepte plus de devis.")
        serializer.save(professional=user)


class RequestQuoteListView(generics.ListAPIView):
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        service_request = get_object_or_404(ServiceRequest, pk=self.kwargs["request_id"])
        user = self.request.user
        if user.role == User.Role.CLIENT:
            if service_request.client_id != user.pk:
                raise PermissionDenied("Cette demande ne vous appartient pas.")
            return Quote.objects.filter(service_request=service_request).select_related(
                "professional"
            )
        if user.role == User.Role.PROFESSIONAL:
            return Quote.objects.filter(
                service_request=service_request, professional=user
            ).select_related("professional")
        raise PermissionDenied("Rôle non autorisé.")


class QuoteAcceptView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            quote = accept_quote(pk, request.user)
        except (Quote.DoesNotExist, ServiceRequest.DoesNotExist):
            return Response({"detail": "Devis introuvable."}, status=404)
        except (DjangoPermissionDenied, ValidationError) as exc:
            detail = getattr(exc, "messages", [str(exc)])[0]
            return Response(
                {"detail": detail}, status=403 if isinstance(exc, DjangoPermissionDenied) else 400
            )
        return Response(QuoteSerializer(quote).data)
