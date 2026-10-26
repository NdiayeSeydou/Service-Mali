from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from rest_framework import generics, permissions, views
from rest_framework.response import Response

from accounts.models import User
from payments.disputes import InvalidDisputeOutcome, resolve_dispute
from payments.services import PaymentRejected

from .models import ServiceRequest
from .serializers import ServiceRequestSerializer, TransitionSerializer
from .services import transition_request


class ServiceRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = ServiceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == User.Role.CLIENT:
            return ServiceRequest.objects.filter(client=user).prefetch_related("state_history")
        if user.role == User.Role.PROFESSIONAL:
            from quotes.models import Quote

            return (
                ServiceRequest.objects.filter(
                    Q(status=ServiceRequest.Status.PUBLISHED)
                    | Q(quotes__professional=user, quotes__status=Quote.Status.ACCEPTED)
                )
                .distinct()
                .select_related("client")
            )
        return ServiceRequest.objects.all().select_related("client")

    def perform_create(self, serializer):
        if self.request.user.role != User.Role.CLIENT:
            raise PermissionDenied("Seuls les clients peuvent publier une demande.")
        serializer.save(client=self.request.user)


class ServiceRequestTransitionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        data = TransitionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = transition_request(
                pk,
                data.validated_data["status"],
                request.user,
                note=data.validated_data.get("note", ""),
            )
        except (ServiceRequest.DoesNotExist, PermissionDenied, ValidationError) as exc:
            detail = getattr(exc, "messages", [str(exc)])[0]
            return Response(
                {"detail": detail},
                status=404
                if isinstance(exc, ServiceRequest.DoesNotExist)
                else 403
                if isinstance(exc, PermissionDenied)
                else 400,
            )
        return Response(ServiceRequestSerializer(result).data)


class DisputeResolutionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            result = resolve_dispute(
                pk,
                actor=request.user,
                outcome=request.data.get("outcome"),
                professional_gross_xof=request.data.get("professional_gross_xof"),
            )
        except ServiceRequest.DoesNotExist:
            return Response({"detail": "Demande introuvable."}, status=404)
        except (PermissionDenied, InvalidDisputeOutcome, PaymentRejected) as exc:
            detail = getattr(exc, "messages", [str(exc)])[0]
            return Response(
                {"detail": detail}, status=403 if isinstance(exc, PermissionDenied) else 400
            )
        return Response(result)
