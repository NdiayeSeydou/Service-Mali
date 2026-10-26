from rest_framework import serializers

from .models import ProfessionalSubscription, SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ("id", "name", "price_xof", "duration_days")


class ProfessionalSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProfessionalSubscription
        fields = ("id", "plan", "status", "starts_at", "expires_at", "is_active", "created_at")
