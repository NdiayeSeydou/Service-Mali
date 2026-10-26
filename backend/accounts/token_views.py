from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import LoginTokenSerializer


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [LoginThrottle]
    serializer_class = LoginTokenSerializer
