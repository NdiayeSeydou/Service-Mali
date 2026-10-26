from django.urls import path

from .views import QuoteMessageListCreateView

urlpatterns = [
    path("<int:quote_id>/messages/", QuoteMessageListCreateView.as_view(), name="quote-messages"),
]
