from django.db import transaction
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User
from requests_app.models import ServiceRequest

from .models import Review
from .serializers import ReviewSerializer


class ReviewCreateView(generics.CreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        if user.role != User.Role.CLIENT:
            raise PermissionDenied("Seul un client peut laisser un avis.")
        service_request = serializer.validated_data["service_request"]
        if service_request.client_id != user.pk:
            raise PermissionDenied("Cette prestation ne vous appartient pas.")
        service_request = ServiceRequest.objects.select_for_update().get(pk=service_request.pk)
        if service_request.status != ServiceRequest.Status.FUNDS_RELEASED:
            raise ValidationError("Un avis est possible après la validation de la prestation.")
        if Review.objects.filter(service_request=service_request).exists():
            raise ValidationError("Un seul avis est autorisé par prestation.")
        quote = (
            service_request.quotes.filter(status="ACCEPTED").select_related("professional").first()
        )
        if quote is None:
            raise ValidationError("Aucun professionnel retenu pour cette prestation.")
        review = serializer.save(
            service_request=service_request, client=user, professional=quote.professional
        )
        from notifications.services import notify_user

        notify_user(
            quote.professional,
            event="REVIEW_RECEIVED",
            subject="Vous avez reçu un nouvel avis",
            body=f"Vous avez reçu un avis {review.rating}/5 après la prestation {service_request.pk}.",
            dedupe_key=f"review:{review.pk}:received:{quote.professional_id}",
        )


class ProfessionalReviewListView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Review.objects.select_related("client", "professional", "service_request")

    def get_queryset(self):
        return self.queryset.filter(professional_id=self.kwargs["professional_id"])
