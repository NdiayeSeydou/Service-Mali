from django.urls import path

from .views import PaymentCheckoutView, PaymentDetailView, PaymentWebhookView, SandboxCheckoutView

urlpatterns = [
    path("checkout/", PaymentCheckoutView.as_view()),
    path("webhooks/<str:provider_code>/", PaymentWebhookView.as_view()),
    path("sandbox/checkout/<str:reference>/", SandboxCheckoutView.as_view()),
    path("<uuid:pk>/", PaymentDetailView.as_view()),
]
