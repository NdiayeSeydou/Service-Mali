from django.urls import path

from .views import QuoteAcceptView, QuoteCreateView

urlpatterns = [
    path("", QuoteCreateView.as_view(), name="quote-create"),
    path("<int:pk>/accept/", QuoteAcceptView.as_view(), name="quote-accept"),
]
