from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .token_views import ThrottledTokenObtainPairView
from .views import (
    GalleryCreateView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfessionalProfileListView,
    ProfessionalVerificationView,
    ProfileView,
    RegisterView,
)

urlpatterns = [
    path("register/", RegisterView.as_view()),
    path("login/", ThrottledTokenObtainPairView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
    path("me/", MeView.as_view()),
    path("password-reset/", PasswordResetRequestView.as_view()),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view()),
    path("professionals/", ProfessionalProfileListView.as_view()),
    path("professionals/me/", ProfileView.as_view()),
    path("professionals/me/gallery/", GalleryCreateView.as_view()),
    path("admin/professionals/<int:pk>/verification/", ProfessionalVerificationView.as_view()),
]
