import pytest
from rest_framework.test import APIClient

from accounts.models import User
from requests_app.models import ServiceRequest

pytestmark = pytest.mark.django_db


def test_admin_dashboard_requires_admin_role_and_reports_core_totals():
    customer = User.objects.create_user(
        username="dashboard-client",
        email="dashboard-client@example.com",
        password="SecurePass!2026",
    )
    ServiceRequest.objects.create(client=customer, category="Électricité", description="Panne")
    api = APIClient()
    api.force_authenticate(customer)
    assert api.get("/api/admin/dashboard/").status_code == 403

    administrator = User.objects.create_user(
        username="dashboard-admin",
        email="dashboard-admin@example.com",
        password="SecurePass!2026",
        role=User.Role.ADMIN,
    )
    assert administrator.is_staff
    administrator.role = User.Role.CLIENT
    administrator.save(update_fields=["role"])
    administrator.refresh_from_db()
    assert not administrator.is_staff
    administrator.role = User.Role.ADMIN
    administrator.save(update_fields=["role"])
    administrator.refresh_from_db()
    api.force_authenticate(administrator)
    response = api.get("/api/admin/dashboard/")
    assert response.status_code == 200
    assert response.data["users"]["clients"] == 1
    assert response.data["requests"]["total"] == 1
    assert response.data["requests"]["disputes_open"] == 0
    assert response.data["payments"]["escrow_xof"] == 0
    assert response.data["notifications"]["failed"] == 0
