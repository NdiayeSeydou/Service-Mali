import pytest
from rest_framework.test import APIClient

from accounts.models import ProfessionalProfile, User
from requests_app.models import ServiceRequest

pytestmark = pytest.mark.django_db


def create_request(client):
    return ServiceRequest.objects.create(
        client=client, category="Plomberie", description="Fuite d’eau"
    )


def test_unverified_professional_cannot_submit_quote():
    pro = User.objects.create_user(
        username="pro",
        email="pro@example.com",
        password="SecurePass!2026",
        role=User.Role.PROFESSIONAL,
    )
    ProfessionalProfile.objects.create(user=pro)
    client_user = User.objects.create_user(
        username="client", email="client@example.com", password="SecurePass!2026"
    )
    service_request = create_request(client_user)
    api = APIClient()
    api.force_authenticate(pro)
    response = api.post(
        "/api/quotes/",
        {"request_id": service_request.pk, "price_xof": 10000, "estimated_days": 2},
        format="json",
    )
    assert response.status_code == 403
    assert "vérifié" in response.data["detail"].lower()


def test_verified_professional_can_create_quote():
    pro = User.objects.create_user(
        username="verified",
        email="verified@example.com",
        password="SecurePass!2026",
        role=User.Role.PROFESSIONAL,
    )
    ProfessionalProfile.objects.create(
        user=pro, verification_status=ProfessionalProfile.VerificationStatus.VERIFIED
    )
    client_user = User.objects.create_user(
        username="client2", email="client2@example.com", password="SecurePass!2026"
    )
    service_request = create_request(client_user)
    api = APIClient()
    api.force_authenticate(pro)
    response = api.post(
        "/api/quotes/",
        {"request_id": service_request.pk, "price_xof": 25000, "estimated_days": 3},
        format="json",
    )
    assert response.status_code == 201


def test_accepting_one_quote_closes_other_quotes_and_prevents_second_acceptance():
    from django.core.exceptions import ValidationError

    from quotes.models import Quote
    from quotes.services import accept_quote

    customer = User.objects.create_user(
        username="buyer", email="buyer@example.com", password="SecurePass!2026"
    )
    request = create_request(customer)
    professionals = [
        User.objects.create_user(
            username=f"pro{i}",
            email=f"pro{i}@example.com",
            password="SecurePass!2026",
            role=User.Role.PROFESSIONAL,
        )
        for i in range(3)
    ]
    quotes = [
        Quote.objects.create(
            service_request=request,
            professional=professional,
            price_xof=10000 + index,
            estimated_days=2,
        )
        for index, professional in enumerate(professionals)
    ]

    accepted = accept_quote(quotes[0].pk, customer)

    assert accepted.status == Quote.Status.ACCEPTED
    assert list(
        Quote.objects.filter(service_request=request)
        .order_by("pk")
        .values_list("status", flat=True)
    ) == [Quote.Status.ACCEPTED, Quote.Status.CLOSED, Quote.Status.CLOSED]
    with pytest.raises(ValidationError, match="n’accepte plus"):
        accept_quote(quotes[1].pk, customer)
    assert Quote.objects.filter(service_request=request, status=Quote.Status.ACCEPTED).count() == 1


def test_quote_conversation_is_private_to_client_and_quoted_professional():
    from rest_framework.test import APIClient

    from quotes.models import Quote

    customer = User.objects.create_user(
        username="owner", email="owner@example.com", password="SecurePass!2026"
    )
    pro = User.objects.create_user(
        username="messaging-pro",
        email="mp@example.com",
        password="SecurePass!2026",
        role=User.Role.PROFESSIONAL,
    )
    outsider = User.objects.create_user(
        username="outsider", email="out@example.com", password="SecurePass!2026"
    )
    request = create_request(customer)
    quote = Quote.objects.create(
        service_request=request, professional=pro, price_xof=12000, estimated_days=2
    )
    api = APIClient()
    api.force_authenticate(pro)
    sent = api.post(
        f"/api/quotes/{quote.pk}/messages/",
        {"body": "Bonjour, je peux passer demain."},
        format="json",
    )
    assert sent.status_code == 201
    api.force_authenticate(customer)
    assert api.get(f"/api/quotes/{quote.pk}/messages/").status_code == 200
    api.force_authenticate(outsider)
    assert api.get(f"/api/quotes/{quote.pk}/messages/").status_code == 403
    assert (
        api.post(
            f"/api/quotes/{quote.pk}/messages/", {"body": "Message intrus"}, format="json"
        ).status_code
        == 403
    )
