from django.urls import path

from .views import ProfessionalReviewListView, ReviewCreateView

urlpatterns = [
    path("", ReviewCreateView.as_view(), name="review-create"),
    path(
        "professionals/<int:professional_id>/",
        ProfessionalReviewListView.as_view(),
        name="professional-reviews",
    ),
]
