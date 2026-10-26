from django.urls import path

from .views import ActivePlanView, MySubscriptionView, SubscriptionCheckoutView

urlpatterns = [
    path("plans/", ActivePlanView.as_view()),
    path("me/", MySubscriptionView.as_view()),
    path("checkout/", SubscriptionCheckoutView.as_view()),
]
