import re

import pytest
from django.core import mail
from rest_framework.test import APIClient

from accounts.models import ProfessionalProfile, User

pytestmark = pytest.mark.django_db


def register(client, role="CLIENT", email="user@example.com"):
    return client.post(
        "/api/auth/register/",
        {
            "email": email,
            "username": email.split("@")[0],
            "password": "SecurePass!2026",
            "role": role,
        },
        format="json",
    )


def test_client_registration():
    response = register(APIClient())
    assert response.status_code == 201
    assert response.data["role"] == User.Role.CLIENT
    assert not ProfessionalProfile.objects.filter(user__email="user@example.com").exists()


def test_professional_registration_creates_pending_profile():
    response = register(APIClient(), "PROFESSIONNEL", "pro@example.com")
    assert response.status_code == 201
    assert (
        ProfessionalProfile.objects.get(user__email="pro@example.com").verification_status
        == "EN_ATTENTE"
    )


def test_admin_verification_and_access_control():
    pro = User.objects.create_user(
        username="pro", email="pro@x.com", password="SecurePass!2026", role=User.Role.PROFESSIONAL
    )
    profile = ProfessionalProfile.objects.create(user=pro)
    client = APIClient()
    client.force_authenticate(pro)
    assert (
        client.post(
            f"/api/auth/admin/professionals/{profile.pk}/verification/",
            {"action": "verify"},
            format="json",
        ).status_code
        == 403
    )
    admin = User.objects.create_superuser(
        username="root", email="root@x.com", password="SecurePass!2026"
    )
    client.force_authenticate(admin)
    assert (
        client.post(
            f"/api/auth/admin/professionals/{profile.pk}/verification/",
            {"action": "verify"},
            format="json",
        ).data["verification_status"]
        == "VERIFIE"
    )


def test_password_reset_email_token_updates_password():
    user = User.objects.create_user(
        username="reset", email="reset@example.com", password="SecurePass!2026"
    )
    client = APIClient()
    assert (
        client.post("/api/auth/password-reset/", {"email": user.email}, format="json").status_code
        == 200
    )
    assert len(mail.outbox) == 1
    uid = re.search(r"uid=([^&]+)", mail.outbox[0].body).group(1)
    token = re.search(r"token=([^\s]+)", mail.outbox[0].body).group(1)
    response = client.post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "new_password": "OtherSecure!2026"},
        format="json",
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password("OtherSecure!2026")


def test_login_returns_jwt_and_refreshes():
    User.objects.create_user(
        username="login",
        email="login@example.com",
        password="SecurePass!2026",
        role=User.Role.PROFESSIONAL,
    )
    client = APIClient()
    response = client.post(
        "/api/auth/login/",
        {"email": "login@example.com", "password": "SecurePass!2026"},
        format="json",
    )
    assert response.status_code == 200
    assert "access" in response.data and "refresh" in response.data
    refreshed = client.post(
        "/api/auth/refresh/", {"refresh": response.data["refresh"]}, format="json"
    )
    assert refreshed.status_code == 200 and "access" in refreshed.data
