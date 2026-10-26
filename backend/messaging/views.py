from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions

from quotes.models import Quote
from requests_app.models import ServiceRequest

from .models import Message
from .serializers import MessageSerializer


class QuoteMessageListCreateView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_quote(self):
        return get_object_or_404(
            Quote.objects.select_related(
                "service_request", "professional", "service_request__client"
            ),
            pk=self.kwargs["quote_id"],
        )

    def _check_participant(self, quote):
        user = self.request.user
        if user.pk not in {quote.professional_id, quote.service_request.client_id}:
            raise PermissionDenied("Cette conversation est réservée aux participants du devis.")

    def get_queryset(self):
        quote = self.get_quote()
        self._check_participant(quote)
        return Message.objects.filter(quote=quote).select_related("sender")

    def perform_create(self, serializer):
        quote = self.get_quote()
        self._check_participant(quote)
        if quote.status not in {Quote.Status.SENT, Quote.Status.ACCEPTED}:
            raise PermissionDenied("Cette conversation est clôturée avec le devis.")
        if quote.service_request.status not in {
            ServiceRequest.Status.PUBLISHED,
            ServiceRequest.Status.QUOTE_ACCEPTED,
            ServiceRequest.Status.ESCROW_PAID,
            ServiceRequest.Status.IN_PROGRESS,
            ServiceRequest.Status.FINISHED_BY_PRO,
            ServiceRequest.Status.VALIDATED_BY_CLIENT,
        }:
            raise PermissionDenied("Cette conversation n’accepte plus de nouveaux messages.")
        message = serializer.save(quote=quote, sender=self.request.user)
        recipient = (
            quote.service_request.client
            if self.request.user.pk == quote.professional_id
            else quote.professional
        )
        from notifications.services import notify_user

        notify_user(
            recipient,
            event="MESSAGE_RECEIVED",
            subject="Vous avez reçu un nouveau message",
            body=f"Vous avez reçu un nouveau message au sujet du devis {quote.pk}.",
            dedupe_key=f"message:{message.pk}:received:{recipient.pk}",
        )
