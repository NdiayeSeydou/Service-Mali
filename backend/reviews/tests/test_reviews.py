import pytest
from rest_framework.test import APIClient

from accounts.models import User
from quotes.models import Quote
from requests_app.models import ServiceRequest

pytestmark = pytest.mark.django_db


def setup_request(status):
    client = User.objects.create_user(
        username="review-client", email="review-client@example.com", password="SecurePass!2026"
    )
    professional = User.objects.create_user(
        username="review-pro",
        email="review-pro@example.com",
        password="SecurePass!2026",
        role=User.Role.PROFESSIONAL,
    )
    request = ServiceRequest.objects.create(
        client=client, category="Plomberie", description="Fuite", status=status
    )
    quote = Quote.objects.create(
        service_request=request,
        professional=professional,
        price_xof=10000,
        estimated_days=2,
        status=Quote.Status.ACCEPTED,
    )
    return client, professional, request, quote


def test_review_requires_released_validated_service_and_can_only_be_submitted_once():
    client, professional, request, _ = setup_request(ServiceRequest.Status.FINISHED_BY_PRO)
    api = APIClient()
    api.force_authenticate(client)
    payload = {"request_id": request.pk, "rating": 5, "comment": "Très bon travail"}

    assert api.post("/api/reviews/", payload, format="json").status_code == 400
    request.status = ServiceRequest.Status.FUNDS_RELEASED
    request.save(update_fields=["status"])
    response = api.post("/api/reviews/", payload, format="json")
    assert response.status_code == 201
    assert response.data["professional"] == professional.pk
    assert api.post("/api/reviews/", payload, format="json").status_code == 400
    assert api.get(f"/api/reviews/professionals/{professional.pk}/").data["count"] == 1


def test_professional_cannot_write_review():
    _, professional, request, _ = setup_request(ServiceRequest.Status.FUNDS_RELEASED)
    api = APIClient()
    api.force_authenticate(professional)
    response = api.post("/api/reviews/", {"request_id": request.pk, "rating": 5}, format="json")
    assert response.status_code == 403
