from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from rest_framework import permissions, views
from rest_framework.response import Response

from .models import Payment
from .providers import InvalidWebhookSignature, ProviderError
from .serializers import PaymentCheckoutSerializer, PaymentSerializer
from .services import (
    PaymentRejected,
    create_service_checkout,
    process_payment_webhook,
    sandbox_confirm_payment,
)


class PaymentCheckoutView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = PaymentCheckoutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            payment = create_service_checkout(
                request.user,
                values["request_id"],
                values["provider"],
                values["success_url"],
                values["error_url"],
            )
        except (PaymentRejected, DjangoPermissionDenied, Payment.DoesNotExist) as exc:
            detail = getattr(exc, "messages", [str(exc)])[0]
            return Response(
                {"detail": detail}, status=403 if isinstance(exc, DjangoPermissionDenied) else 400
            )
        return Response(PaymentSerializer(payment).data, status=201)


class PaymentDetailView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            payment = Payment.objects.get(pk=pk, customer=request.user)
        except Payment.DoesNotExist:
            return Response({"detail": "Paiement introuvable."}, status=404)
        return Response(PaymentSerializer(payment).data)


class PaymentWebhookView(views.APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, provider_code):
        headers = {
            "WAVE": request.META.get("HTTP_WAVE_SIGNATURE", ""),
            "ORANGE_MONEY": request.META.get("HTTP_X_ORANGE_SIGNATURE", ""),
        }
        try:
            result = process_payment_webhook(
                provider_code.upper(), request.body, headers.get(provider_code.upper(), "")
            )
        except (PaymentRejected, ProviderError, ValueError) as exc:
            detail = getattr(exc, "messages", [str(exc)])[0]
            status_code = 401 if isinstance(exc, InvalidWebhookSignature) else 400
            return Response({"detail": detail}, status=status_code)
        return Response(result)


class SandboxCheckoutView(views.APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, reference):
        if not settings.DEBUG or getattr(settings, "PAYMENT_MODE", "sandbox") != "sandbox":
            return Response(status=404)
        session = Payment.objects.filter(provider_reference=reference).first()
        if session is None:
            return Response({"detail": "Session inconnue."}, status=404)
        return Response(
            {
                "reference": reference,
                "amount_xof": session.amount_xof,
                "currency": session.currency,
                "status": session.status,
                "confirmation_endpoint": request.build_absolute_uri(),
            }
        )

    def post(self, request, reference):
        if not settings.DEBUG or getattr(settings, "PAYMENT_MODE", "sandbox") != "sandbox":
            return Response(status=404)
        try:
            result = sandbox_confirm_payment(reference)
        except (PaymentRejected, Payment.DoesNotExist) as exc:
            detail = getattr(exc, "messages", [str(exc)])[0]
            return Response({"detail": detail}, status=400)
        return Response(result)
