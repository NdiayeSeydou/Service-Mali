from rest_framework import generics, permissions, views
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounts.models import ProfessionalProfile, User
from payments.services import PaymentRejected, create_subscription_checkout

from .models import ProfessionalSubscription, SubscriptionPlan
from .serializers import ProfessionalSubscriptionSerializer, SubscriptionPlanSerializer


class ActivePlanView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = SubscriptionPlanSerializer

    def get_queryset(self):
        if not SubscriptionPlan.objects.filter(active=True).exists():
            SubscriptionPlan.objects.create(
                name="Premium mensuel", price_xof=5000, duration_days=30
            )
        return SubscriptionPlan.objects.filter(active=True).order_by("price_xof")


class MySubscriptionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        subscription = (
            ProfessionalSubscription.objects.filter(user=request.user)
            .select_related("plan")
            .first()
        )
        return Response(
            ProfessionalSubscriptionSerializer(subscription).data if subscription else None
        )


class SubscriptionCheckoutView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if (
            request.user.role != User.Role.PROFESSIONAL
            or not ProfessionalProfile.objects.filter(
                user=request.user,
                verification_status=ProfessionalProfile.VerificationStatus.VERIFIED,
            ).exists()
        ):
            raise PermissionDenied("Un compte professionnel vérifié est requis pour Premium.")
        try:
            plan = SubscriptionPlan.objects.get(pk=request.data.get("plan_id"), active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({"detail": "Formule Premium indisponible."}, status=404)
        try:
            payment = create_subscription_checkout(
                request.user,
                plan,
                request.data.get("provider", "WAVE"),
                request.data.get("success_url", "http://localhost:5173/premium?success=1"),
                request.data.get("error_url", "http://localhost:5173/premium?error=1"),
            )
        except (ValueError, PaymentRejected) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {
                "payment_id": payment.pk,
                "checkout_url": payment.checkout_url,
                "status": payment.status,
            },
            status=201,
        )
