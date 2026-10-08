from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from properties.models import Property, Unit
from rentals.models import RentalAgreement, Tenant


class RentalsWebTests(TestCase):
    """Rentals features are served through Django views and templates."""

    def setUp(self):
        self.owner = User.objects.create_user(
            "rentals_owner", "+252615000001", "SafePassword123!",
            full_name="Rentals Owner", is_approved=True,
        )
        self.property = Property.objects.create(
            owner=self.owner, name="Rentals Villa", location="Mogadishu",
        )
        self.unit = Unit.objects.create(property=self.property, unit_number="U1")
        self.tenant = Tenant.objects.create(owner=self.owner, full_name="Customer Rental")
        self.agreement = RentalAgreement.objects.create(
            tenant=self.tenant, property=self.property, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("600.00"), status="active",
        )
        self.client.login(username="rentals_owner", password="SafePassword123!")

    def test_tenant_list_page_renders(self):
        response = self.client.get(reverse("web-tenants"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer Rental")

    def test_tenant_create_page_renders(self):
        response = self.client.get(reverse("web-tenant-create"))
        self.assertEqual(response.status_code, 200)

    def test_agreement_list_page_renders(self):
        response = self.client.get(reverse("web-agreements"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rentals Villa")

    def test_agreement_create_page_renders_for_tenant(self):
        response = self.client.get(reverse("web-agreement-create"), {"tenant": self.tenant.pk})
        self.assertEqual(response.status_code, 200)

    def test_units_by_property_endpoint_lists_available_units(self):
        response = self.client.get(
            reverse("web-units-by-property"), {"property_id": self.property.pk}
        )
        self.assertEqual(response.status_code, 200)
        units = response.json()["units"]
        self.assertEqual([unit["id"] for unit in units], [self.unit.pk])

    def test_anonymous_rentals_pages_redirect_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("web-tenants"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/login/"))


class RemovedRestApiRoutesTests(TestCase):
    """The unused REST API layer was removed; these routes must stay gone."""

    removed_routes = (
        "/api/v1/properties/",
        "/api/v1/properties/1/",
        "/api/v1/rentals/",
        "/api/v1/rentals/1/",
        "/api/v1/rentals/1/end-rental/",
        "/api/v1/rentals/1/pay/",
        "/api/v1/finance/",
        "/api/v1/finance/expenses/",
        "/api/v1/accounts/register/",
        "/api/v1/accounts/login/",
        "/api/v1/accounts/me/",
        "/api/v1/accounting/reports/chart-of-accounts/",
    )

    def test_removed_api_routes_return_not_found(self):
        for route in self.removed_routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 404)

    def test_plain_django_json_routes_under_api_prefix_survive(self):
        response = self.client.get(reverse("web-units-by-property"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/login/"))
