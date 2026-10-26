from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.admin_dashboard import AdminDashboardView
from accounts.private_views import private_identity_document

urlpatterns = [
    path("private-identity/<int:user_id>/", private_identity_document),
    path("admin/", admin.site.urls),
    path("api/admin/dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("api/auth/", include("accounts.urls")),
    path("api/requests/", include("requests_app.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/subscriptions/", include("subscriptions.urls")),
    path("api/reviews/", include("reviews.urls")),
    path("api/quotes/", include("quotes.urls")),
    path("api/quotes/", include("messaging.urls")),
    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),
    path("api/schema/", SpectacularAPIView.as_view()),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
]
