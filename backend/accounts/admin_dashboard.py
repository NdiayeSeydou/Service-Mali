from django.db.models import Avg, Count, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import ProfessionalProfile, User
from accounts.permissions import IsAdminRole
from notifications.models import NotificationDelivery
from payments.models import EscrowHold, Payment
from requests_app.models import ServiceRequest
from reviews.models import Review
from subscriptions.models import ProfessionalSubscription


class AdminDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        now = timezone.now()
        request_statuses = dict(
            ServiceRequest.objects.values_list("status").annotate(total=Count("id"))
        )
        payment_statuses = dict(Payment.objects.values_list("status").annotate(total=Count("id")))
        notifications = dict(
            NotificationDelivery.objects.values_list("status").annotate(total=Count("id"))
        )
        return Response(
            {
                "users": {
                    "clients": User.objects.filter(role=User.Role.CLIENT, is_active=True).count(),
                    "professionals": User.objects.filter(
                        role=User.Role.PROFESSIONAL, is_active=True
                    ).count(),
                    "admins": User.objects.filter(role=User.Role.ADMIN, is_active=True).count(),
                },
                "professional_verification": {
                    "pending": ProfessionalProfile.objects.filter(
                        verification_status=ProfessionalProfile.VerificationStatus.PENDING
                    ).count(),
                    "verified": ProfessionalProfile.objects.filter(
                        verification_status=ProfessionalProfile.VerificationStatus.VERIFIED
                    ).count(),
                    "rejected": ProfessionalProfile.objects.filter(
                        verification_status=ProfessionalProfile.VerificationStatus.REJECTED
                    ).count(),
                },
                "requests": {
                    "total": ServiceRequest.objects.count(),
                    "by_status": request_statuses,
                    "disputes_open": ServiceRequest.objects.filter(
                        status=ServiceRequest.Status.IN_DISPUTE
                    ).count(),
                },
                "payments": {
                    "by_status": payment_statuses,
                    "escrow_xof": Payment.objects.filter(
                        purpose=Payment.Purpose.SERVICE, status=Payment.Status.PAID
                    ).aggregate(total=Sum("amount_xof"))["total"]
                    or 0,
                    "frozen_escrows": EscrowHold.objects.filter(
                        status=EscrowHold.Status.FROZEN
                    ).count(),
                },
                "reviews": {
                    "total": Review.objects.count(),
                    "average_rating": Review.objects.aggregate(value=Avg("rating"))["value"],
                },
                "subscriptions_active": ProfessionalSubscription.objects.filter(
                    status=ProfessionalSubscription.Status.ACTIVE, expires_at__gt=now
                ).count(),
                "notifications": {
                    "queued": notifications.get(NotificationDelivery.Status.QUEUED, 0),
                    "failed": notifications.get(NotificationDelivery.Status.FAILED, 0),
                },
                "generated_at": now,
            }
        )
