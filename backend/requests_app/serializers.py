from rest_framework import serializers

from .models import ServiceRequest


class ServiceRequestSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ServiceRequest
        fields = (
            "id",
            "client",
            "category",
            "description",
            "neighborhood",
            "budget_xof",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "client", "status", "created_at", "updated_at")


class TransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ServiceRequest.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=250)
