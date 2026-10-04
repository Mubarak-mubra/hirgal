from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from finance.models import Payment
from properties.models import Property
from rentals.models import RentalAgreement, Tenant


class CheckTenantPaidViewOwnershipTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice", phone_number="+252611000001",
            password="Password123!", full_name="Alice Cabdiraxmaan", is_approved=True,
        )
        self.bob = User.objects.create_user(
            username="bob", phone_number="+252611000002",
            password="Password123!", full_name="Bile Cabdilaahi", is_approved=True,
        )
        self.alice_tenant = Tenant.objects.create(owner=self.alice, full_name="Customer Alice")
        self.bob_tenant = Tenant.objects.create(owner=self.bob, full_name="Customer Bob")
        alice_property = Property.objects.create(owner=self.alice, name="Alice Villa", location="Mogadishu")
        bob_property = Property.objects.create(owner=self.bob, name="Bob Villa", location="Mogadishu")
        self.alice_agreement = RentalAgreement.objects.create(
            tenant=self.alice_tenant, property=alice_property, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        self.bob_agreement = RentalAgreement.objects.create(
            tenant=self.bob_tenant, property=bob_property, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("700.00"),
        )
        Payment.objects.create(
            rental_agreement=self.alice_agreement, amount=Decimal("400.00"),
            payment_date=date.today(),
        )
        Payment.objects.create(
            rental_agreement=self.bob_agreement, amount=Decimal("650.00"),
            payment_date=date.today(),
        )
        self.url = reverse("web-check-tenant-paid")

    def test_returns_own_payment_data(self):
        self.client.login(username="alice", password="Password123!")
        response = self.client.get(self.url, {"tenant_id": self.alice_tenant.pk})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["paid"])
        self.assertEqual(data["tenant_name"], "Customer Alice")
        self.assertEqual(data["total_paid"], 400.0)
        self.assertEqual(data["count"], 1)

    def test_does_not_leak_other_users_payment_data(self):
        self.client.login(username="alice", password="Password123!")
        response = self.client.get(self.url, {"tenant_id": self.bob_tenant.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"paid": False})

    def test_missing_tenant_id_returns_paid_false(self):
        self.client.login(username="alice", password="Password123!")
        response = self.client.get(self.url)
        self.assertEqual(response.json(), {"paid": False})
