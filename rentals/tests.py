from datetime import date
from unittest.mock import patch

from django.test import RequestFactory
from rest_framework.test import APITestCase

from accounts.models import User
from rentals.models import Tenant
from rentals.serializers import TenantRegistrationSerializer


class TenantRegistrationOwnershipTests(APITestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.owner = User.objects.create_user("owner_a", "+252615000001", "SafePassword123!", full_name="Owner A")
        self.manager = User.objects.create_user("manager_b", "+252615000002", "SafePassword123!", full_name="Manager B")
        self.manager.managed_account = self.owner
        self.manager.save()
        self.outsider = User.objects.create_user("owner_c", "+252615000003", "SafePassword123!", full_name="Owner C")

    def register_tenant(self, user, phone_number):
        request = self.factory.post("/api/v1/rentals/")
        request.user = user
        serializer = TenantRegistrationSerializer(
            data={
                "full_name": "Customer One",
                "phone_number": phone_number,
                "property_id": 1,
                "agreed_monthly_rent": "300.00",
                "start_date": date(2026, 1, 1),
            },
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid())
        # RentalAgreement.objects.create is mocked only because it currently
        # fails on an unrelated known field issue (separate task, out of scope).
        with patch("rentals.serializers.RentalAgreement.objects.create"):
            return serializer.save()

    def test_root_owner_registration_stays_under_owner(self):
        tenant = self.register_tenant(self.owner, "+252615000091")
        self.assertEqual(tenant.owner, self.owner)

    def test_manager_registration_uses_owner_boundary(self):
        tenant = self.register_tenant(self.manager, "+252615000092")
        self.assertEqual(tenant.owner, self.owner)
        self.assertNotEqual(tenant.owner, self.manager)

    def test_unrelated_user_registration_stays_under_own_boundary(self):
        tenant = self.register_tenant(self.outsider, "+252615000093")
        self.assertEqual(tenant.owner, self.outsider)
