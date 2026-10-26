from rest_framework import serializers

from .models import (
    LedgerEntry,
    Payment,
)


class PaymentCheckoutSerializer(serializers.Serializer):
    request_id = serializers.IntegerField(min_value=1)
    provider = serializers.ChoiceField(choices=Payment.Provider.choices)
    success_url = serializers.URLField()
    error_url = serializers.URLField()


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "provider",
            "purpose",
            "request",
            "quote",
            "amount_xof",
            "currency",
            "checkout_url",
            "status",
            "created_at",
            "paid_at",
            "settled_at",
        )
        read_only_fields = fields


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = (
            "id",
            "payment",
            "entry_type",
            "source_account",
            "destination_account",
            "amount_xof",
            "created_at",
        )
