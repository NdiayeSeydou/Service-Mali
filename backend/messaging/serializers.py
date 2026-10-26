from rest_framework import serializers

from .models import Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ("id", "quote", "sender", "body", "created_at")
        read_only_fields = ("id", "quote", "sender", "created_at")
