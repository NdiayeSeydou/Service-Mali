from rest_framework import serializers

from requests_app.models import ServiceRequest

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    request_id = serializers.PrimaryKeyRelatedField(
        source="service_request", queryset=ServiceRequest.objects.all()
    )
    client = serializers.PrimaryKeyRelatedField(read_only=True)
    client_name = serializers.CharField(source="client.get_full_name", read_only=True)
    professional = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "request_id",
            "client",
            "client_name",
            "professional",
            "rating",
            "comment",
            "created_at",
        )
        read_only_fields = ("id", "client", "client_name", "professional", "created_at")
