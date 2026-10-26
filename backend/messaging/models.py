from django.conf import settings
from django.db import models


class Message(models.Model):
    quote = models.ForeignKey("quotes.Quote", on_delete=models.PROTECT, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_messages"
    )
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
