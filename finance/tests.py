from datetime import date
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from finance.models import GeneralExpense, Payment
from properties.models import Property
from rentals.models import RentalAgreement, Tenant


class FinanceApiOwnershipTests(APITestCase):
    expenses_url = "/api/v1/finance/expenses/"
    payments_url = "/api/v1/finance/"

    def setUp(self):
        self.owner = User.objects.create_user("owner_a", "+252615000001", "SafePassword123!", full_name="Owner A")
        self.manager = User.objects.create_user("manager_b", "+252615000002", "SafePassword123!", full_name="Manager B")
        self.manager.managed_account = self.owner
        self.manager.save()
        self.outsider = User.objects.create_user("owner_c", "+252615000003", "SafePassword123!", full_name="Owner C")
        self.property = Property.objects.create(owner=self.owner, name="Owner A Block", location="Hodan")
        self.outsider_property = Property.objects.create(owner=self.outsider, name="Owner C Block", location="Hodan")
        self.expense = GeneralExpense.objects.create(
            property=self.property, title="Roof repair", category="repair", amount=Decimal("50.00"), expense_date=date(2026, 9, 1)
        )
        self.outsider_expense = GeneralExpense.objects.create(
            property=self.outsider_property, title="Other repair", category="repair", amount=Decimal("70.00"), expense_date=date(2026, 9, 1)
        )
        tenant = Tenant.objects.create(owner=self.owner, full_name="Customer One", phone_number="+252615000011")
        agreement = RentalAgreement.objects.create(
            tenant=tenant, property=self.property, start_date=date(2026, 1, 1), monthly_rent=Decimal("300.00"), status="active"
        )
        self.payment = Payment.objects.create(rental_agreement=agreement, amount=Decimal("300.00"), payment_date=date(2026, 9, 1))

    def test_root_owner_reads_own_financial_data(self):
        self.client.force_authenticate(self.owner)
        expenses = self.client.get(self.expenses_url)
        self.assertEqual(expenses.status_code, status.HTTP_200_OK)
        self.assertEqual([e["id"] for e in expenses.data], [self.expense.id])
        payments = self.client.get(self.payments_url + "?month=9&year=2026")
        self.assertEqual([p["id"] for p in payments.data], [self.payment.id])

    def test_manager_reads_owner_payment_and_expense_boundary(self):
        self.client.force_authenticate(self.manager)
        expenses = self.client.get(self.expenses_url)
        self.assertEqual([e["id"] for e in expenses.data], [self.expense.id])
        payments = self.client.get(self.payments_url + "?month=9&year=2026")
        self.assertEqual([p["id"] for p in payments.data], [self.payment.id])
        summary = self.client.get(self.payments_url + "summary/?month=9&year=2026")
        self.assertEqual(summary.data["total_tenants"], 1)
        self.assertEqual(summary.data["paid_tenants"], 1)
        monthly = self.client.get(self.payments_url + "monthly-summary/")
        self.assertEqual([m["month"] for m in monthly.data], ["2026-09"])

    def test_manager_creates_expense_on_owner_property(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(self.expenses_url, {"property_id": self.property.id, "title": "Paint", "amount": "20.00"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        expense = GeneralExpense.objects.get(pk=response.data["id"])
        self.assertEqual(expense.property.owner, self.owner)
        blocked = self.client.post(self.expenses_url, {"property_id": self.outsider_property.id, "title": "Other", "amount": "20.00"})
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(GeneralExpense.objects.filter(title="Other").exists())

    def test_unrelated_user_cannot_read_or_create_on_other_boundary(self):
        self.client.force_authenticate(self.outsider)
        expenses = self.client.get(self.expenses_url)
        self.assertEqual([e["id"] for e in expenses.data], [self.outsider_expense.id])
        self.assertEqual(self.client.get(self.payments_url + "?month=9&year=2026").data, [])
        response = self.client.post(self.expenses_url, {"property_id": self.property.id, "title": "Sneaky", "amount": "10.00"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(GeneralExpense.objects.filter(title="Sneaky").exists())
