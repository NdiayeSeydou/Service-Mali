import pytest
from django.utils import timezone

from accounts.models import ProfessionalProfile, User
from payments.models import LedgerEntry, Payment
from payments.services import create_subscription_checkout, sandbox_confirm_payment
from subscriptions.models import ProfessionalSubscription, SubscriptionPlan
from subscriptions.tasks import expire_subscriptions

pytestmark = pytest.mark.django_db


def test_premium_activates_only_after_verified_sandbox_payment():
    user = User.objects.create_user(
        username="premium",
        email="premium@example.com",
        password="SecurePass!2026",
        role=User.Role.PROFESSIONAL,
    )
    ProfessionalProfile.objects.create(
        user=user, verification_status=ProfessionalProfile.VerificationStatus.VERIFIED
    )
    plan = SubscriptionPlan.objects.create(name="Premium mensuel", price_xof=5000, duration_days=30)
    payment = create_subscription_checkout(
        user,
        plan,
        Payment.Provider.ORANGE_MONEY,
        "https://app.test/success",
        "https://app.test/error",
    )
    assert not ProfessionalSubscription.objects.get(user=user).is_active
    sandbox_confirm_payment(payment.provider_reference)
    subscription = ProfessionalSubscription.objects.get(user=user)
    assert subscription.is_active
    assert subscription.expires_at > timezone.now()
    assert LedgerEntry.objects.filter(
        payment=payment, entry_type=LedgerEntry.Type.SUBSCRIPTION_PURCHASE
    ).exists()


def test_expired_premium_is_removed_by_scheduled_task():
    user = User.objects.create_user(
        username="expired",
        email="expired@example.com",
        password="SecurePass!2026",
        role=User.Role.PROFESSIONAL,
    )
    plan = SubscriptionPlan.objects.create(name="Premium", price_xof=5000, duration_days=30)
    subscription = ProfessionalSubscription.objects.create(
        user=user,
        plan=plan,
        status=ProfessionalSubscription.Status.ACTIVE,
        starts_at=timezone.now(),
        expires_at=timezone.now() - timezone.timedelta(seconds=1),
    )
    assert expire_subscriptions.run() == 1
    subscription.refresh_from_db()
    assert subscription.status == ProfessionalSubscription.Status.EXPIRED
    assert not subscription.is_active
