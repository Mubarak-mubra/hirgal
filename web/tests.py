import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounting.models import Account, Invoice, InvoiceLine, JournalEntry, JournalEntryLine
from accounting.services import (
    DEFAULT_COA, get_rental_income_account, link_bank_account_to_ledger,
    post_invoice, seed_default_chart_of_accounts,
)
from finance.models import BankAccount, Payment, GeneralExpense, MaintenanceRepair
from properties.models import Property, PropertyAsset, PropertyType, Room, Unit
from rentals.models import RentalAgreement, Tenant

from .chatbot import explore_financial_summary
from .forms import InvoiceForm, InvoiceLineFormSet


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


class AgreementsByTenantViewOwnershipTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice2", phone_number="+252611000011",
            password="Password123!", full_name="Alice Cabdiraxmaan", is_approved=True,
        )
        self.bob = User.objects.create_user(
            username="bob2", phone_number="+252611000012",
            password="Password123!", full_name="Bile Cabdilaahi", is_approved=True,
        )
        self.alice_tenant = Tenant.objects.create(owner=self.alice, full_name="Customer Alice")
        self.bob_tenant = Tenant.objects.create(owner=self.bob, full_name="Customer Bob")
        alice_property = Property.objects.create(owner=self.alice, name="Alice Villa", location="Mogadishu")
        bob_property = Property.objects.create(owner=self.bob, name="Bob Villa", location="Mogadishu")
        self.alice_agreement = RentalAgreement.objects.create(
            tenant=self.alice_tenant, property=alice_property, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"), status="active",
        )
        self.bob_agreement = RentalAgreement.objects.create(
            tenant=self.bob_tenant, property=bob_property, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("700.00"), status="active",
        )
        self.url = reverse("web-agreements-by-tenant")

    def test_returns_own_tenants_active_agreements(self):
        self.client.login(username="alice2", password="Password123!")
        response = self.client.get(self.url, {"tenant_id": self.alice_tenant.pk})
        self.assertEqual(response.status_code, 200)
        agreements = response.json()["agreements"]
        self.assertEqual(len(agreements), 1)
        self.assertEqual(agreements[0]["id"], self.alice_agreement.pk)
        self.assertIn("Alice Villa", agreements[0]["label"])

    def test_does_not_leak_other_users_agreements(self):
        self.client.login(username="alice2", password="Password123!")
        response = self.client.get(self.url, {"tenant_id": self.bob_tenant.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"agreements": []})

    def test_missing_tenant_id_returns_empty_agreements(self):
        self.client.login(username="alice2", password="Password123!")
        response = self.client.get(self.url)
        self.assertEqual(response.json(), {"agreements": []})


class UnitsByPropertyViewOwnershipTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice3", phone_number="+252611000021",
            password="Password123!", full_name="Alice Cabdiraxmaan", is_approved=True,
        )
        self.bob = User.objects.create_user(
            username="bob3", phone_number="+252611000022",
            password="Password123!", full_name="Bile Cabdilaahi", is_approved=True,
        )
        alice_type = PropertyType.objects.create(owner=self.alice, name="Apartment", has_units=True)
        bob_type = PropertyType.objects.create(owner=self.bob, name="Apartment", has_units=True)
        self.alice_property = Property.objects.create(
            owner=self.alice, name="Alice Towers", location="Mogadishu", property_type=alice_type,
        )
        self.bob_property = Property.objects.create(
            owner=self.bob, name="Bob Towers", location="Mogadishu", property_type=bob_type,
        )
        self.alice_unit_free = Unit.objects.create(property=self.alice_property, unit_number="A1")
        self.alice_unit_rented = Unit.objects.create(property=self.alice_property, unit_number="A2")
        self.bob_unit = Unit.objects.create(property=self.bob_property, unit_number="B1")
        alice_tenant = Tenant.objects.create(owner=self.alice, full_name="Customer Alice")
        RentalAgreement.objects.create(
            tenant=alice_tenant, property=self.alice_property, unit=self.alice_unit_rented,
            start_date=date(2026, 1, 1), monthly_rent=Decimal("500.00"), status="active",
        )
        self.url = reverse("web-units-by-property")

    def test_returns_own_property_units(self):
        self.client.login(username="alice3", password="Password123!")
        response = self.client.get(self.url, {"property_id": self.alice_property.pk})
        self.assertEqual(response.status_code, 200)
        units = response.json()["units"]
        unit_numbers = [u["unit_number"] for u in units]
        self.assertIn("A1", unit_numbers)
        self.assertIn(self.alice_unit_free.pk, [u["id"] for u in units])

    def test_does_not_leak_other_users_property_units(self):
        self.client.login(username="alice3", password="Password123!")
        response = self.client.get(self.url, {"property_id": self.bob_property.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"units": []})

    def test_missing_property_id_returns_empty_units(self):
        self.client.login(username="alice3", password="Password123!")
        response = self.client.get(self.url)
        self.assertEqual(response.json(), {"units": []})

    def test_active_rented_unit_is_not_listed(self):
        self.client.login(username="alice3", password="Password123!")
        response = self.client.get(self.url, {"property_id": self.alice_property.pk})
        unit_numbers = [u["unit_number"] for u in response.json()["units"]]
        self.assertIn("A1", unit_numbers)
        self.assertNotIn("A2", unit_numbers)


class LoginChartOfAccountsOwnershipTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="login_owner", phone_number="+252615000201", password="SafePassword123!",
            full_name="Owner", is_approved=True,
        )
        self.manager = User.objects.create_user(
            username="login_manager", phone_number="+252615000202", password="SafePassword123!",
            full_name="Manager", is_approved=True,
        )
        self.manager.managed_account = self.owner
        self.manager.save()

    def login(self, user):
        return self.client.post(
            reverse("web-login"),
            {"username_or_phone": user.username, "password": "SafePassword123!"},
        )

    def test_owner_login_without_chart_seeds_under_owner(self):
        response = self.login(self.owner)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Account.objects.filter(owner=self.owner).count(), len(DEFAULT_COA))

    def test_owner_login_with_existing_chart_continues_normally(self):
        seed_default_chart_of_accounts(self.owner)
        response = self.login(self.owner)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Account.objects.filter(owner=self.owner).count(), len(DEFAULT_COA))

    def test_manager_login_does_not_create_manager_owned_chart(self):
        seed_default_chart_of_accounts(self.owner)
        response = self.login(self.manager)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Account.objects.filter(owner=self.manager).count(), 0)
        self.assertEqual(Account.objects.filter(owner=self.owner).count(), len(DEFAULT_COA))

    def test_manager_login_gate_uses_effective_data_owner(self):
        seed_default_chart_of_accounts(self.owner)
        with patch("web.views.seed_default_chart_of_accounts") as mock_seed:
            response = self.login(self.manager)
        self.assertEqual(response.status_code, 302)
        mock_seed.assert_not_called()


class EffectiveDataOwnerIsolationTests(TestCase):
    """Owner/Manager data access must go through the effective data owner."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "owner_a", "+252617000001", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "manager_a", "+252617000002", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "owner_b", "+252617000003", self.password, full_name="Owner B", is_approved=True,
        )
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Tower", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Tower", location="Mogadishu")

    def test_owner_can_access_own_data(self):
        self.client.login(username="owner_a", password=self.password)
        detail = self.client.get(reverse("web-property-detail", args=[self.prop_a.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertIn("Alpha Tower", detail.content.decode())
        listing = self.client.get(reverse("web-properties"))
        self.assertIn("Alpha Tower", listing.content.decode())
        self.assertNotIn("Beta Tower", listing.content.decode())

    def test_manager_can_access_owners_data(self):
        self.client.login(username="manager_a", password=self.password)
        detail = self.client.get(reverse("web-property-detail", args=[self.prop_a.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertIn("Alpha Tower", detail.content.decode())
        listing = self.client.get(reverse("web-properties"))
        self.assertIn("Alpha Tower", listing.content.decode())

    def test_manager_creates_data_under_owner(self):
        prop_type = PropertyType.objects.create(owner=self.owner_a, name="Tower Block")
        self.client.login(username="manager_a", password=self.password)
        response = self.client.post(reverse("web-property-create"), {
            "name": "Gamma Place",
            "location": "Mogadishu",
            "property_type": prop_type.pk,
        })
        self.assertEqual(response.status_code, 302)
        created = Property.objects.get(name="Gamma Place")
        self.assertEqual(created.owner, self.owner_a)

    def test_manager_cannot_access_other_owners_data(self):
        self.client.login(username="manager_a", password=self.password)
        detail = self.client.get(reverse("web-property-detail", args=[self.prop_b.pk]))
        self.assertEqual(detail.status_code, 404)
        listing = self.client.get(reverse("web-properties"))
        self.assertNotIn("Beta Tower", listing.content.decode())
        units = self.client.get(reverse("web-units-by-property"), {"property_id": self.prop_b.pk})
        self.assertEqual(units.json(), {"units": []})

    def test_owner_a_and_owner_b_are_isolated(self):
        self.client.login(username="owner_a", password=self.password)
        self.assertEqual(self.client.get(reverse("web-property-detail", args=[self.prop_b.pk])).status_code, 404)
        listing_a = self.client.get(reverse("web-properties"))
        self.assertIn("Alpha Tower", listing_a.content.decode())
        self.assertNotIn("Beta Tower", listing_a.content.decode())

        self.client.logout()
        self.client.login(username="owner_b", password=self.password)
        self.assertEqual(self.client.get(reverse("web-property-detail", args=[self.prop_a.pk])).status_code, 404)
        listing_b = self.client.get(reverse("web-properties"))
        self.assertIn("Beta Tower", listing_b.content.decode())
        self.assertNotIn("Alpha Tower", listing_b.content.decode())

    def test_owner_behavior_remains_unchanged(self):
        self.assertEqual(self.owner_a.get_data_owner(), self.owner_a)
        self.client.login(username="owner_a", password=self.password)
        edit = self.client.get(reverse("web-property-edit", args=[self.prop_a.pk]))
        self.assertEqual(edit.status_code, 200)
        prop_type = PropertyType.objects.create(owner=self.owner_a, name="Owner Type")
        response = self.client.post(reverse("web-property-create"), {
            "name": "Owner Made",
            "location": "Mogadishu",
            "property_type": prop_type.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Property.objects.get(name="Owner Made").owner, self.owner_a)


class ChatbotAccountsPayableOwnershipTests(TestCase):
    """Chatbot financial summary must only count the caller's payables."""

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "owner_a", "+252617000011", "SafePassword123!", full_name="Owner A", is_approved=True,
        )
        self.owner_b = User.objects.create_user(
            "owner_b", "+252617000012", "SafePassword123!", full_name="Owner B", is_approved=True,
        )
        acc_a = Account.objects.create(owner=self.owner_a, code="2010", name="Accounts Payable", category="liability")
        acc_b = Account.objects.create(owner=self.owner_b, code="2010", name="Accounts Payable", category="liability")
        je_a = JournalEntry.objects.create(owner=self.owner_a, date=date.today(), status="posted")
        JournalEntryLine.objects.create(journal_entry=je_a, account=acc_a, credit=Decimal("500"))
        je_b = JournalEntry.objects.create(owner=self.owner_b, date=date.today(), status="posted")
        JournalEntryLine.objects.create(journal_entry=je_b, account=acc_b, credit=Decimal("300"))

    def test_accounts_payable_scoped_to_callers_owner(self):
        result = json.loads(explore_financial_summary(self.owner_b))
        self.assertEqual(result["accounts_payable"], 300.0)

    def test_owner_a_summary_only_counts_own_payables(self):
        result = json.loads(explore_financial_summary(self.owner_a))
        self.assertEqual(result["accounts_payable"], 500.0)


class ReportSourceLookupOwnershipTests(TestCase):
    """Report source-link lookups must not resolve another owner's records."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "owner_a", "+252617000021", self.password, full_name="Owner A", is_approved=True,
        )
        self.owner_b = User.objects.create_user(
            "owner_b", "+252617000022", self.password, full_name="Owner B", is_approved=True,
        )
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Tower", location="Mogadishu")
        tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Tenant B", phone_number="+252618000001")
        self.invoice_b = Invoice.objects.create(
            owner=self.owner_b, tenant=tenant_b, invoice_number="INV-2026-0001",
            date=date.today(), due_date=date.today(),
        )
        self.expense_b = GeneralExpense.objects.create(
            property=self.prop_b, title="B expense", category="repair",
            amount=Decimal("100"), expense_date=date.today(),
        )
        self.repair_b = MaintenanceRepair.objects.create(
            property=self.prop_b, title="B repair", repair_cost=Decimal("50"),
            reported_date=date.today(),
        )

    def test_ar_report_does_not_resolve_other_owners_invoice(self):
        ar_a = Account.objects.create(owner=self.owner_a, code="1200", name="Accounts Receivable", category="asset")
        je = JournalEntry.objects.create(
            owner=self.owner_a, date=date.today(),
            reference=self.invoice_b.invoice_number, status="posted",
        )
        JournalEntryLine.objects.create(journal_entry=je, account=ar_a, debit=Decimal("100"))
        self.client.login(username="owner_a", password=self.password)
        response = self.client.get(reverse("web-ar"))
        items = response.context["items"]
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["source_url"])

    def test_ar_report_still_links_own_invoice(self):
        ar_b = Account.objects.create(owner=self.owner_b, code="1200", name="Accounts Receivable", category="asset")
        je = JournalEntry.objects.create(
            owner=self.owner_b, date=date.today(),
            reference=self.invoice_b.invoice_number, status="posted",
        )
        JournalEntryLine.objects.create(journal_entry=je, account=ar_b, debit=Decimal("100"))
        self.client.login(username="owner_b", password=self.password)
        response = self.client.get(reverse("web-ar"))
        items = response.context["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_url"], "/xisaabiyadda/biilasha/%d/" % self.invoice_b.pk)

    def test_sales_report_detail_does_not_resolve_other_owners_invoice(self):
        prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Sales", location="Mogadishu")
        rev_a = Account.objects.create(owner=self.owner_a, code="4010", name="Rental Income", category="revenue")
        je = JournalEntry.objects.create(
            owner=self.owner_a, date=date.today(),
            reference=self.invoice_b.invoice_number, status="posted",
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=rev_a, credit=Decimal("100"), property=prop_a,
        )
        self.client.login(username="owner_a", password=self.password)
        response = self.client.get(reverse("web-sales-report-detail", args=[prop_a.pk]))
        self.assertEqual(response.status_code, 200)
        items = response.context["items"]
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["source_url"])

    def test_ap_report_does_not_resolve_other_owners_expense(self):
        ap_a = Account.objects.create(owner=self.owner_a, code="2010", name="Accounts Payable", category="liability")
        je = JournalEntry.objects.create(
            owner=self.owner_a, date=date.today(),
            reference="EXP-%d" % self.expense_b.pk, status="posted",
        )
        JournalEntryLine.objects.create(journal_entry=je, account=ap_a, credit=Decimal("75"))
        self.client.login(username="owner_a", password=self.password)
        response = self.client.get(reverse("web-ap"))
        items = response.context["items"]
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["source_url"])

    def test_ap_report_does_not_resolve_other_owners_repair(self):
        ap_a = Account.objects.create(owner=self.owner_a, code="2010", name="Accounts Payable", category="liability")
        je = JournalEntry.objects.create(
            owner=self.owner_a, date=date.today(),
            reference="REP-%d" % self.repair_b.pk, status="posted",
        )
        JournalEntryLine.objects.create(journal_entry=je, account=ap_a, credit=Decimal("60"))
        self.client.login(username="owner_a", password=self.password)
        response = self.client.get(reverse("web-ap"))
        items = response.context["items"]
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["source_url"])


class InvoiceNumberGenerationTests(TestCase):
    """Invoice numbering runs per effective data owner, year by year."""

    password = "SafePassword123!"

    def setUp(self):
        self.year = date.today().year
        self.today = date.today()
        self.owner_a = User.objects.create_user(
            "inv_owner_a", "+252619000011", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "inv_manager_a", "+252619000012", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "inv_owner_b", "+252619000013", self.password, full_name="Owner B", is_approved=True,
        )
        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Tenant A", phone_number="+252619000041")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Tenant B", phone_number="+252619000042")

    def make_invoice(self, owner, tenant, number):
        return Invoice.objects.create(
            owner=owner, tenant=tenant, invoice_number=number,
            date=self.today, due_date=self.today,
        )

    def test_invoice_number_sequences_are_independent_per_owner(self):
        first_a = InvoiceForm(user=self.owner_a).fields["invoice_number"].initial
        self.assertEqual(first_a, "INV-%d-0001" % self.year)
        self.make_invoice(self.owner_a, self.tenant_a, first_a)

        first_b = InvoiceForm(user=self.owner_b).fields["invoice_number"].initial
        self.assertEqual(first_b, "INV-%d-0001" % self.year)
        self.make_invoice(self.owner_b, self.tenant_b, first_b)

        second_a = InvoiceForm(user=self.owner_a).fields["invoice_number"].initial
        self.assertEqual(second_a, "INV-%d-0002" % self.year)

    def test_manager_uses_effective_owners_sequence_and_ownership(self):
        self.make_invoice(self.owner_a, self.tenant_a, "INV-%d-0001" % self.year)
        self.client.login(username="inv_manager_a", password=self.password)

        page = self.client.get(reverse("web-invoice-create"))
        self.assertEqual(page.status_code, 200)
        initial = page.context["form"].fields["invoice_number"].initial
        self.assertEqual(initial, "INV-%d-0002" % self.year)

        response = self.client.post(reverse("web-invoice-create"), {
            "tenant": self.tenant_a.pk,
            "invoice_number": initial,
            "date": self.today.isoformat(),
            "due_date": self.today.isoformat(),
            "status": "draft",
            "notes": "",
            f"{InvoiceLineFormSet().prefix}-TOTAL_FORMS": "0",
            f"{InvoiceLineFormSet().prefix}-INITIAL_FORMS": "0",
            f"{InvoiceLineFormSet().prefix}-MIN_NUM_FORMS": "0",
            f"{InvoiceLineFormSet().prefix}-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.get(invoice_number=initial)
        self.assertEqual(invoice.owner, self.owner_a)

    def test_ar_report_lookup_resolves_own_invoice_despite_cross_owner_duplicates(self):
        number = "INV-%d-0002" % self.year
        inv_a = self.make_invoice(self.owner_a, self.tenant_a, number)
        self.make_invoice(self.owner_b, self.tenant_b, number)

        ar_a = Account.objects.create(owner=self.owner_a, code="1200", name="Accounts Receivable", category="asset")
        je = JournalEntry.objects.create(
            owner=self.owner_a, date=self.today, reference=number, status="posted",
        )
        JournalEntryLine.objects.create(journal_entry=je, account=ar_a, debit=Decimal("100"))

        self.client.login(username="inv_owner_a", password=self.password)
        response = self.client.get(reverse("web-ar"))
        items = response.context["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_url"], "/xisaabiyadda/biilasha/%d/" % inv_a.pk)


class PaymentSourceLinkOwnershipTests(TestCase):
    """Payment detail endpoints and report payment source links stay within the effective data owner."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "pay_owner_a", "+252617000041", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "pay_manager_a", "+252617000042", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "pay_owner_b", "+252617000043", self.password, full_name="Owner B", is_approved=True,
        )

        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Customer A")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Customer B")
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")
        self.agreement_a = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        self.agreement_b = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=self.prop_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("700.00"),
        )
        # post_payment signal creates owner-scoped journal entries and ledger accounts.
        self.payment_a = Payment.objects.create(
            rental_agreement=self.agreement_a, amount=Decimal("400.00"), payment_date=date.today(),
        )
        self.payment_b = Payment.objects.create(
            rental_agreement=self.agreement_b, amount=Decimal("650.00"), payment_date=date.today(),
        )
        self.invoice_a = Invoice.objects.create(
            owner=self.owner_a, tenant=self.tenant_a, invoice_number="INV-2026-9001",
            date=date.today(), due_date=date.today(),
        )
        self.invoice_b = Invoice.objects.create(
            owner=self.owner_b, tenant=self.tenant_b, invoice_number="INV-2026-9001",
            date=date.today(), due_date=date.today(),
        )
        self.ar_payment_a = Payment.objects.create(
            rental_agreement=self.agreement_a, amount=Decimal("100.00"),
            payment_date=date.today(), invoice=self.invoice_a,
        )
        self.ar_payment_b = Payment.objects.create(
            rental_agreement=self.agreement_b, amount=Decimal("150.00"),
            payment_date=date.today(), invoice=self.invoice_b,
        )

    @staticmethod
    def _payment_link_pks(urls):
        pks = set()
        for url in urls:
            if url and "/lacag-bixinta/" in url:
                pks.add(int(url.rstrip("/").rsplit("/", 1)[-1]))
        return pks

    @staticmethod
    def _gl_payment_urls(response):
        return [
            t["source_url"]
            for acc in response.context["ledger"]
            for t in acc["transactions"]
            if t["source_url"]
        ]

    def test_owner_cannot_resolve_other_owners_payment(self):
        self.client.login(username="pay_owner_a", password=self.password)
        self.assertEqual(self.client.get(reverse("web-payment-detail", args=[self.payment_b.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("web-payment-edit", args=[self.payment_b.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("web-payment-delete", args=[self.payment_b.pk])).status_code, 404)
        self.assertTrue(Payment.objects.filter(pk=self.payment_b.pk).exists())
        self.assertEqual(self.client.get(reverse("web-payment-detail", args=[self.payment_a.pk])).status_code, 200)

    def test_manager_resolves_managed_owners_payment(self):
        self.client.login(username="pay_manager_a", password=self.password)
        response = self.client.get(reverse("web-payment-detail", args=[self.payment_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["payment"].pk, self.payment_a.pk)

    def test_manager_cannot_resolve_other_owners_payment(self):
        self.client.login(username="pay_manager_a", password=self.password)
        self.assertEqual(self.client.get(reverse("web-payment-detail", args=[self.payment_b.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("web-payment-edit", args=[self.payment_b.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("web-payment-delete", args=[self.payment_b.pk])).status_code, 404)
        self.assertTrue(Payment.objects.filter(pk=self.payment_b.pk).exists())

    def test_report_payment_source_links_stay_within_effective_owner(self):
        own_a = {self.payment_a.pk, self.ar_payment_a.pk}
        own_b = {self.payment_b.pk, self.ar_payment_b.pk}

        self.client.login(username="pay_owner_a", password=self.password)
        gl_pks = self._payment_link_pks(self._gl_payment_urls(self.client.get(reverse("web-general-ledger"))))
        self.assertTrue(gl_pks)
        self.assertTrue(gl_pks.issubset(own_a))

        ar = self.client.get(reverse("web-ar"))
        ar_pks = self._payment_link_pks([i["source_url"] for i in ar.context["items"]])
        self.assertIn(self.ar_payment_a.pk, ar_pks)
        self.assertNotIn(self.ar_payment_b.pk, ar_pks)

        bank_a = Account.objects.get(owner=self.owner_a, code="1020")
        ledger = self.client.get(reverse("web-account-ledger", args=[bank_a.pk]))
        ledger_pks = self._payment_link_pks([t["source_url"] for t in ledger.context["transactions"]])
        self.assertTrue(ledger_pks)
        self.assertTrue(ledger_pks.issubset(own_a))

        self.client.logout()
        self.client.login(username="pay_manager_a", password=self.password)
        manager_pks = self._payment_link_pks(self._gl_payment_urls(self.client.get(reverse("web-general-ledger"))))
        self.assertTrue(manager_pks)
        self.assertTrue(manager_pks.issubset(own_a))

        self.client.logout()
        self.client.login(username="pay_owner_b", password=self.password)
        b_pks = self._payment_link_pks(self._gl_payment_urls(self.client.get(reverse("web-general-ledger"))))
        self.assertTrue(b_pks)
        self.assertTrue(b_pks.issubset(own_b))
        self.assertFalse(b_pks & own_a)

    def test_sales_report_payment_link_cannot_resolve_foreign_payment(self):
        rev_a = Account.objects.get(owner=self.owner_a, code="4010")
        je = JournalEntry.objects.create(
            owner=self.owner_a, date=date.today(),
            reference="PAY-%d" % self.payment_b.pk, status="posted",
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=rev_a, credit=Decimal("50"), property=self.prop_a,
        )
        self.client.login(username="pay_owner_a", password=self.password)
        response = self.client.get(reverse("web-sales-report-detail", args=[self.prop_a.pk]))
        self.assertEqual(response.status_code, 200)
        source_urls = [i["source_url"] for i in response.context["items"]]
        # A PAY-prefixed reference with no backing Payment emits no link at all.
        crafted = [i for i in response.context["items"] if i["reference"] == "PAY-%d" % self.payment_b.pk]
        self.assertEqual(len(crafted), 1)
        self.assertIsNone(crafted[0]["source_url"])
        self.assertNotIn("/lacagaha/%d/" % self.payment_b.pk, source_urls)
        self.assertNotIn(reverse("web-payment-detail", args=[self.payment_b.pk]), source_urls)
        self.assertFalse([u for u in source_urls if u and u.startswith("/lacagaha/")])
        self.assertEqual(
            self.client.get(reverse("web-payment-detail", args=[self.payment_b.pk])).status_code, 404,
        )

    def test_existing_payment_source_links_still_resolve(self):
        self.client.login(username="pay_owner_a", password=self.password)
        gl_urls = self._gl_payment_urls(self.client.get(reverse("web-general-ledger")))
        own_url = "/lacag-bixinta/%d/" % self.payment_a.pk
        self.assertIn(own_url, gl_urls)
        detail = self.client.get(own_url)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["payment"].pk, self.payment_a.pk)

        ar = self.client.get(reverse("web-ar"))
        ar_url = "/lacag-bixinta/%d/" % self.ar_payment_a.pk
        self.assertIn(ar_url, [i["source_url"] for i in ar.context["items"]])
        self.assertEqual(self.client.get(ar_url).status_code, 200)

        self.client.logout()
        self.client.login(username="pay_manager_a", password=self.password)
        self.assertEqual(self.client.get(own_url).status_code, 200)
        self.assertEqual(self.client.get(ar_url).status_code, 200)


class SalesReportPaymentLinkTests(TestCase):
    """Sales Report PAY rows must emit real, effective-owner payment detail links."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "srl_owner_a", "+252617000051", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "srl_manager_a", "+252617000052", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "srl_owner_b", "+252617000053", self.password, full_name="Owner B", is_approved=True,
        )

        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Customer A")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Customer B")
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")
        self.agreement_a = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        self.agreement_b = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=self.prop_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("700.00"),
        )

        # Real posting path: post_payment signal -> owner-scoped journal entry.
        # Form-style payment: reference PAY-YYYY-NNNN (yearly sequence, NOT the pk).
        self.payment_a = Payment.objects.create(
            rental_agreement=self.agreement_a, amount=Decimal("400.00"),
            payment_date=date(2026, 6, 15), reference_number="PAY-2026-0042",
        )
        # Fallback path: payment saved without a reference -> journal reference PAY-<pk>.
        self.payment_a2 = Payment.objects.create(
            rental_agreement=self.agreement_a, amount=Decimal("60.00"),
            payment_date=date(2026, 6, 20),
        )
        self.payment_b = Payment.objects.create(
            rental_agreement=self.agreement_b, amount=Decimal("650.00"),
            payment_date=date(2026, 6, 15), reference_number="PAY-2026-0042",
        )

        self.report_url = reverse("web-sales-report-detail", args=[self.prop_a.pk])
        self.range_qs = "?start_date=2026-01-01&end_date=2026-12-31"

    @staticmethod
    def _source_urls(response):
        return [i["source_url"] for i in response.context["items"]]

    @staticmethod
    def _payment_pks(urls):
        return {
            int(u.rstrip("/").rsplit("/", 1)[-1])
            for u in urls if u and "/lacag-bixinta/" in u
        }

    def test_owner_report_emits_real_payment_detail_url(self):
        self.client.login(username="srl_owner_a", password=self.password)
        response = self.client.get(self.report_url + self.range_qs)
        self.assertEqual(response.status_code, 200)
        urls = self._source_urls(response)
        expected = "/lacag-bixinta/%d/" % self.payment_a.pk
        self.assertIn("PAY-2026-0042", [i["reference"] for i in response.context["items"]])
        self.assertIn(expected, urls)
        self.assertFalse([u for u in urls if u and u.startswith("/lacagaha/")])
        self.assertNotIn("0042", expected)

    def test_generated_link_resolves_for_owner(self):
        self.client.login(username="srl_owner_a", password=self.password)
        expected = "/lacag-bixinta/%d/" % self.payment_a.pk
        self.assertIn(expected, self._source_urls(self.client.get(self.report_url + self.range_qs)))
        detail = self.client.get(expected)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["payment"].pk, self.payment_a.pk)

    def test_manager_resolves_owner_a_generated_payment_link(self):
        self.client.login(username="srl_manager_a", password=self.password)
        response = self.client.get(self.report_url + self.range_qs)
        self.assertEqual(response.status_code, 200)
        expected = "/lacag-bixinta/%d/" % self.payment_a.pk
        self.assertIn(expected, self._source_urls(response))
        detail = self.client.get(expected)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["payment"].pk, self.payment_a.pk)

    def test_owner_cannot_resolve_owner_b_payment(self):
        self.client.login(username="srl_owner_a", password=self.password)
        foreign = reverse("web-payment-detail", args=[self.payment_b.pk])
        self.assertEqual(self.client.get(foreign).status_code, 404)

    def test_owner_report_never_produces_owner_b_payment_link(self):
        self.client.login(username="srl_owner_a", password=self.password)
        urls = self._source_urls(self.client.get(self.report_url + self.range_qs))
        self.assertNotIn(reverse("web-payment-detail", args=[self.payment_b.pk]), urls)
        self.assertFalse([u for u in urls if u and u.startswith("/lacagaha/")])
        own = {self.payment_a.pk, self.payment_a2.pk}
        pks = self._payment_pks(urls)
        self.assertTrue(pks)
        self.assertTrue(pks.issubset(own))

        self.client.logout()
        self.client.login(username="srl_owner_b", password=self.password)
        b_urls = self._source_urls(
            self.client.get(reverse("web-sales-report-detail", args=[self.prop_b.pk]) + self.range_qs)
        )
        self.assertIn(reverse("web-payment-detail", args=[self.payment_b.pk]), b_urls)

    def test_report_link_not_derived_from_pay_sequence(self):
        self.client.login(username="srl_owner_a", password=self.password)
        response = self.client.get(self.report_url + self.range_qs)
        items = [i for i in response.context["items"] if i["reference"] == "PAY-2026-0042"]
        self.assertEqual(len(items), 1)
        url = items[0]["source_url"]
        self.assertEqual(url, reverse("web-payment-detail", args=[self.payment_a.pk]))
        self.assertFalse(url.rstrip("/").endswith("0042"))
        self.assertNotEqual(self.payment_a.pk, 42)
        self.assertEqual(self.client.get("/lacag-bixinta/42/").status_code, 404)

    def test_fallback_reference_payment_link_resolves(self):
        self.client.login(username="srl_owner_a", password=self.password)
        expected = "/lacag-bixinta/%d/" % self.payment_a2.pk
        self.assertIn(expected, self._source_urls(self.client.get(self.report_url + self.range_qs)))
        detail = self.client.get(expected)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["payment"].pk, self.payment_a2.pk)


class ExpenseReportSourceLinkTests(TestCase):
    """Expense Report EXP/REP rows must emit real, effective-owner detail links."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "exr_owner_a", "+252617000061", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "exr_manager_a", "+252617000062", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "exr_owner_b", "+252617000063", self.password, full_name="Owner B", is_approved=True,
        )

        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")

        # Real posting path: GeneralExpense -> post_expense signal -> owner-scoped JournalEntry.
        self.expense_a = GeneralExpense.objects.create(
            property=self.prop_a, title="Office supplies", category="office",
            amount=Decimal("120.00"), expense_date=date(2026, 6, 10),
        )
        self.expense_b = GeneralExpense.objects.create(
            property=self.prop_b, title="Office supplies", category="office",
            amount=Decimal("130.00"), expense_date=date(2026, 6, 10),
        )
        # Real posting path: MaintenanceRepair -> post_repair (repair_cost > 0 posts a JE).
        self.repair_a = MaintenanceRepair.objects.create(
            property=self.prop_a, title="Leaking pipe", category="plumbing",
            repair_cost=Decimal("250.00"), reported_date=date(2026, 6, 12),
        )
        self.repair_b = MaintenanceRepair.objects.create(
            property=self.prop_b, title="Leaking pipe", category="plumbing",
            repair_cost=Decimal("260.00"), reported_date=date(2026, 6, 12),
        )

        self.exp_report_url = reverse(
            "web-expense-report-detail", args=[self.expense_a.expense_account_id]
        )
        self.rep_report_url = reverse(
            "web-expense-report-detail", args=[self.repair_a.expense_account_id]
        )
        self.range_qs = "?start_date=2026-01-01&end_date=2026-12-31"

    @staticmethod
    def _source_urls(response):
        return [i["source_url"] for i in response.context["items"]]

    @staticmethod
    def _link_pks(urls, prefix):
        return {
            int(u.rstrip("/").rsplit("/", 1)[-1])
            for u in urls if u and prefix in u
        }

    def test_expense_report_emits_real_expense_url(self):
        self.client.login(username="exr_owner_a", password=self.password)
        response = self.client.get(self.exp_report_url + self.range_qs)
        self.assertEqual(response.status_code, 200)
        expected = "/kharashka/%d/" % self.expense_a.pk
        self.assertIn("EXP-%d" % self.expense_a.pk, [i["reference"] for i in response.context["items"]])
        self.assertIn(expected, self._source_urls(response))

    def test_owner_resolves_expense_link(self):
        self.client.login(username="exr_owner_a", password=self.password)
        expected = "/kharashka/%d/" % self.expense_a.pk
        self.assertIn(expected, self._source_urls(self.client.get(self.exp_report_url + self.range_qs)))
        detail = self.client.get(expected)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["expense"].pk, self.expense_a.pk)

    def test_manager_resolves_owner_a_expense_link(self):
        self.client.login(username="exr_manager_a", password=self.password)
        response = self.client.get(self.exp_report_url + self.range_qs)
        self.assertEqual(response.status_code, 200)
        expected = "/kharashka/%d/" % self.expense_a.pk
        self.assertIn(expected, self._source_urls(response))
        detail = self.client.get(expected)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["expense"].pk, self.expense_a.pk)

    def test_owner_cannot_resolve_owner_b_expense(self):
        self.client.login(username="exr_owner_a", password=self.password)
        foreign = reverse("web-expense-detail", args=[self.expense_b.pk])
        self.assertEqual(self.client.get(foreign).status_code, 404)

    def test_expense_report_never_generates_owner_b_expense_link(self):
        self.client.login(username="exr_owner_a", password=self.password)
        urls = self._source_urls(self.client.get(self.exp_report_url + self.range_qs))
        self.assertNotIn(reverse("web-expense-detail", args=[self.expense_b.pk]), urls)
        pks = self._link_pks(urls, "/kharashka/")
        self.assertTrue(pks)
        self.assertTrue(pks.issubset({self.expense_a.pk}))

        self.client.logout()
        self.client.login(username="exr_owner_b", password=self.password)
        b_report = reverse("web-expense-report-detail", args=[self.expense_b.expense_account_id])
        b_urls = self._source_urls(self.client.get(b_report + self.range_qs))
        self.assertIn(reverse("web-expense-detail", args=[self.expense_b.pk]), b_urls)

    def test_repair_report_emits_real_repair_url(self):
        self.client.login(username="exr_owner_a", password=self.password)
        response = self.client.get(self.rep_report_url + self.range_qs)
        self.assertEqual(response.status_code, 200)
        expected = "/dayactirka/%d/" % self.repair_a.pk
        self.assertIn("REP-%d" % self.repair_a.pk, [i["reference"] for i in response.context["items"]])
        self.assertIn(expected, self._source_urls(response))

    def test_owner_resolves_repair_link(self):
        self.client.login(username="exr_owner_a", password=self.password)
        expected = "/dayactirka/%d/" % self.repair_a.pk
        self.assertIn(expected, self._source_urls(self.client.get(self.rep_report_url + self.range_qs)))
        detail = self.client.get(expected)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["repair"].pk, self.repair_a.pk)

    def test_manager_resolves_owner_a_repair_link(self):
        self.client.login(username="exr_manager_a", password=self.password)
        response = self.client.get(self.rep_report_url + self.range_qs)
        self.assertEqual(response.status_code, 200)
        expected = "/dayactirka/%d/" % self.repair_a.pk
        self.assertIn(expected, self._source_urls(response))
        detail = self.client.get(expected)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["repair"].pk, self.repair_a.pk)

    def test_owner_cannot_resolve_owner_b_repair(self):
        self.client.login(username="exr_owner_a", password=self.password)
        foreign = reverse("web-maintenance-detail", args=[self.repair_b.pk])
        self.assertEqual(self.client.get(foreign).status_code, 404)

    def test_repair_report_never_generates_owner_b_repair_link(self):
        self.client.login(username="exr_owner_a", password=self.password)
        urls = self._source_urls(self.client.get(self.rep_report_url + self.range_qs))
        self.assertNotIn(reverse("web-maintenance-detail", args=[self.repair_b.pk]), urls)
        pks = self._link_pks(urls, "/dayactirka/")
        self.assertTrue(pks)
        self.assertTrue(pks.issubset({self.repair_a.pk}))

        self.client.logout()
        self.client.login(username="exr_owner_b", password=self.password)
        b_report = reverse("web-expense-report-detail", args=[self.repair_b.expense_account_id])
        b_urls = self._source_urls(self.client.get(b_report + self.range_qs))
        self.assertIn(reverse("web-maintenance-detail", args=[self.repair_b.pk]), b_urls)

    def test_reference_identifier_is_model_pk_not_sequence(self):
        """EXP/REP references embed the model pk itself, and links carry the full pk."""
        self.client.login(username="exr_owner_a", password=self.password)
        exp_items = self.client.get(self.exp_report_url + self.range_qs).context["items"]
        exp = [i for i in exp_items if i["reference"] == "EXP-%d" % self.expense_a.pk]
        self.assertEqual(len(exp), 1)
        self.assertEqual(exp[0]["source_url"], reverse("web-expense-detail", args=[self.expense_a.pk]))
        self.assertEqual(self.client.get(exp[0]["source_url"]).context["expense"].pk, self.expense_a.pk)

        rep_items = self.client.get(self.rep_report_url + self.range_qs).context["items"]
        rep = [i for i in rep_items if i["reference"] == "REP-%d" % self.repair_a.pk]
        self.assertEqual(len(rep), 1)
        self.assertEqual(rep[0]["source_url"], reverse("web-maintenance-detail", args=[self.repair_a.pk]))
        self.assertEqual(self.client.get(rep[0]["source_url"]).context["repair"].pk, self.repair_a.pk)

    def test_sequence_like_reference_emits_no_link(self):
        """A PAY-style sequence reference must not be parsed into an EXP/REP pk URL."""
        acct_5030 = Account.objects.get(owner=self.owner_a, code="5030")
        acct_5010 = Account.objects.get(owner=self.owner_a, code="5010")
        for ref, account in (("EXP-2026-0001", acct_5030), ("REP-2026-0001", acct_5010)):
            je = JournalEntry.objects.create(
                owner=self.owner_a, date=date(2026, 6, 10), reference=ref, status="posted",
            )
            JournalEntryLine.objects.create(journal_entry=je, account=account, debit=Decimal("50"))
        self.client.login(username="exr_owner_a", password=self.password)
        for report_url in (self.exp_report_url, self.rep_report_url):
            urls = self._source_urls(self.client.get(report_url + self.range_qs))
            self.assertFalse([u for u in urls if u and ("2026" in u)])
            self.assertFalse([u for u in urls if u and u.startswith("/kharashka/2026")])
            self.assertFalse([u for u in urls if u and u.startswith("/dayactirka/2026")])

    def test_crafted_foreign_reference_emits_no_link(self):
        """A reference naming another Customer's object emits no link (mirrors AP view)."""
        acct_5030 = Account.objects.get(owner=self.owner_a, code="5030")
        acct_5010 = Account.objects.get(owner=self.owner_a, code="5010")
        crafted = (
            ("EXP-%d" % self.expense_b.pk, acct_5030, self.exp_report_url),
            ("REP-%d" % self.repair_b.pk, acct_5010, self.rep_report_url),
        )
        for ref, account, report_url in crafted:
            je = JournalEntry.objects.create(
                owner=self.owner_a, date=date(2026, 6, 10), reference=ref, status="posted",
            )
            JournalEntryLine.objects.create(journal_entry=je, account=account, debit=Decimal("50"))
        self.client.login(username="exr_owner_a", password=self.password)
        for ref, account, report_url in crafted:
            items = self.client.get(report_url + self.range_qs).context["items"]
            target = [i for i in items if i["reference"] == ref]
            self.assertEqual(len(target), 1)
            self.assertIsNone(target[0]["source_url"])
        self.assertNotIn(
            reverse("web-expense-detail", args=[self.expense_b.pk]),
            self._source_urls(self.client.get(self.exp_report_url + self.range_qs)),
        )
        self.assertNotIn(
            reverse("web-maintenance-detail", args=[self.repair_b.pk]),
            self._source_urls(self.client.get(self.rep_report_url + self.range_qs)),
        )


class AccountsPayableSourceLinkTests(TestCase):
    """AP EXP/REP source links use the real object relationship and never crash the report."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "apl_owner_a", "+252617000071", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "apl_manager_a", "+252617000072", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "apl_owner_b", "+252617000073", self.password, full_name="Owner B", is_approved=True,
        )
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")

        # Unpaid expenses/repairs credit Accounts Payable (2010) -> AP report rows
        # via the real post_expense/post_repair signal path.
        self.expense_a = GeneralExpense.objects.create(
            property=self.prop_a, title="Office supplies", category="office",
            amount=Decimal("120.00"), expense_date=date(2026, 6, 10),
        )
        self.expense_b = GeneralExpense.objects.create(
            property=self.prop_b, title="Office supplies", category="office",
            amount=Decimal("130.00"), expense_date=date(2026, 6, 10),
        )
        self.repair_a = MaintenanceRepair.objects.create(
            property=self.prop_a, title="Leaking pipe", category="plumbing",
            repair_cost=Decimal("250.00"), reported_date=date(2026, 6, 12),
        )
        self.repair_b = MaintenanceRepair.objects.create(
            property=self.prop_b, title="Leaking pipe", category="plumbing",
            repair_cost=Decimal("260.00"), reported_date=date(2026, 6, 12),
        )
        self.range_qs = "?start_date=2026-01-01&end_date=2026-12-31"

    @staticmethod
    def _source_urls(response):
        return [i["source_url"] for i in response.context["items"]]

    @staticmethod
    def _link_pks(urls, prefix):
        return {
            int(u.rstrip("/").rsplit("/", 1)[-1])
            for u in urls if u and prefix in u
        }

    def test_ap_report_emits_real_expense_and_repair_urls(self):
        self.client.login(username="apl_owner_a", password=self.password)
        response = self.client.get(reverse("web-ap") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        items = response.context["items"]
        exp = [i for i in items if i["reference"] == "EXP-%d" % self.expense_a.pk]
        rep = [i for i in items if i["reference"] == "REP-%d" % self.repair_a.pk]
        self.assertEqual(len(exp), 1)
        self.assertEqual(len(rep), 1)
        self.assertEqual(exp[0]["source_url"], reverse("web-expense-detail", args=[self.expense_a.pk]))
        self.assertEqual(rep[0]["source_url"], reverse("web-maintenance-detail", args=[self.repair_a.pk]))

    def test_owner_resolves_ap_links(self):
        self.client.login(username="apl_owner_a", password=self.password)
        urls = self._source_urls(self.client.get(reverse("web-ap") + self.range_qs))
        for url in (
            reverse("web-expense-detail", args=[self.expense_a.pk]),
            reverse("web-maintenance-detail", args=[self.repair_a.pk]),
        ):
            self.assertIn(url, urls)
            detail = self.client.get(url)
            self.assertEqual(detail.status_code, 200)

    def test_manager_resolves_owner_a_ap_links(self):
        self.client.login(username="apl_manager_a", password=self.password)
        response = self.client.get(reverse("web-ap") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        for url in (
            reverse("web-expense-detail", args=[self.expense_a.pk]),
            reverse("web-maintenance-detail", args=[self.repair_a.pk]),
        ):
            self.assertIn(url, self._source_urls(response))
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_owner_and_manager_cannot_resolve_owner_b_ap_targets(self):
        for username in ("apl_owner_a", "apl_manager_a"):
            self.client.login(username=username, password=self.password)
            self.assertEqual(
                self.client.get(reverse("web-expense-detail", args=[self.expense_b.pk])).status_code, 404,
            )
            self.assertEqual(
                self.client.get(reverse("web-maintenance-detail", args=[self.repair_b.pk])).status_code, 404,
            )
            self.client.logout()

    def test_ap_report_never_generates_owner_b_links(self):
        self.client.login(username="apl_owner_a", password=self.password)
        urls = self._source_urls(self.client.get(reverse("web-ap") + self.range_qs))
        self.assertNotIn(reverse("web-expense-detail", args=[self.expense_b.pk]), urls)
        self.assertNotIn(reverse("web-maintenance-detail", args=[self.repair_b.pk]), urls)
        exp_pks = self._link_pks(urls, "/kharashka/")
        rep_pks = self._link_pks(urls, "/dayactirka/")
        self.assertTrue(exp_pks)
        self.assertTrue(rep_pks)
        self.assertTrue(exp_pks.issubset({self.expense_a.pk}))
        self.assertTrue(rep_pks.issubset({self.repair_a.pk}))

        self.client.logout()
        self.client.login(username="apl_owner_b", password=self.password)
        b_urls = self._source_urls(self.client.get(reverse("web-ap") + self.range_qs))
        self.assertIn(reverse("web-expense-detail", args=[self.expense_b.pk]), b_urls)
        self.assertIn(reverse("web-maintenance-detail", args=[self.repair_b.pk]), b_urls)
        self.assertNotIn(reverse("web-expense-detail", args=[self.expense_a.pk]), b_urls)

    def test_malformed_exp_rep_references_do_not_crash_ap_report(self):
        """A non-numeric EXP/REP reference segment must not raise ValueError (HTTP 500)."""
        ap_2010 = Account.objects.get(owner=self.owner_a, code="2010")
        for ref in ("EXP-NEW", "REP-NEW"):
            je = JournalEntry.objects.create(
                owner=self.owner_a, date=date(2026, 6, 10), reference=ref, status="posted",
            )
            JournalEntryLine.objects.create(journal_entry=je, account=ap_2010, credit=Decimal("30"))
        self.client.login(username="apl_owner_a", password=self.password)
        response = self.client.get(reverse("web-ap") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        items = response.context["items"]
        for ref in ("EXP-NEW", "REP-NEW"):
            target = [i for i in items if i["reference"] == ref]
            self.assertEqual(len(target), 1)
            self.assertIsNone(target[0]["source_url"])
        urls = self._source_urls(response)
        self.assertFalse([u for u in urls if u and "NEW" in u])

    def test_deleted_source_objects_leave_no_ap_link(self):
        pk = self.expense_a.pk
        self.expense_a.delete()  # post_delete signal cancels the journal entry
        self.client.login(username="apl_owner_a", password=self.password)
        response = self.client.get(reverse("web-ap") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        items = response.context["items"]
        # Cancelled entries no longer affect the AP report: no row, therefore
        # no link to the deleted object can appear anywhere in the report.
        gone = [i for i in items if i["reference"] == "EXP-%d" % pk]
        self.assertEqual(gone, [])
        urls = self._source_urls(response)
        self.assertFalse([u for u in urls if u and "/kharashka/%d/" % pk in u])
        # the surviving repair link is untouched
        self.assertIn(
            reverse("web-maintenance-detail", args=[self.repair_a.pk]),
            urls,
        )


class CrossReportSourceLinkCoverageTests(TestCase):
    """GL / Account Ledger / Sales emit real invoice, expense, and repair source links."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "xra_owner_a", "+252617000081", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "xra_manager_a", "+252617000082", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "xra_owner_b", "+252617000083", self.password, full_name="Owner B", is_approved=True,
        )
        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Customer A")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Customer B")
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")

        # Real invoice posting path (mirrors InvoiceCreateView: save invoice, save
        # line, then re-post now that lines exist).
        for tenant, prop in ((self.tenant_a, self.prop_a), (self.tenant_b, self.prop_b)):
            agreement = RentalAgreement.objects.create(
                tenant=tenant, property=prop, start_date=date(2026, 1, 1),
                monthly_rent=Decimal("500.00"),
            )
            invoice = Invoice.objects.create(
                owner=tenant.owner, tenant=tenant, property=prop, rental_agreement=agreement,
                invoice_number="INV-2026-9501", date=date(2026, 6, 1), due_date=date(2026, 6, 30),
            )
            InvoiceLine.objects.create(
                invoice=invoice, account=get_rental_income_account(tenant.owner),
                description="Rent", amount=Decimal("500.00"),
            )
            post_invoice(invoice)
        self.invoice_a = Invoice.objects.get(owner=self.owner_a, invoice_number="INV-2026-9501")
        self.invoice_b = Invoice.objects.get(owner=self.owner_b, invoice_number="INV-2026-9501")

        self.expense_a = GeneralExpense.objects.create(
            property=self.prop_a, title="Office supplies", category="office",
            amount=Decimal("120.00"), expense_date=date(2026, 6, 10),
        )
        self.expense_b = GeneralExpense.objects.create(
            property=self.prop_b, title="Office supplies", category="office",
            amount=Decimal("130.00"), expense_date=date(2026, 6, 10),
        )
        self.repair_a = MaintenanceRepair.objects.create(
            property=self.prop_a, title="Leaking pipe", category="plumbing",
            repair_cost=Decimal("250.00"), reported_date=date(2026, 6, 12),
        )
        self.repair_b = MaintenanceRepair.objects.create(
            property=self.prop_b, title="Leaking pipe", category="plumbing",
            repair_cost=Decimal("260.00"), reported_date=date(2026, 6, 12),
        )

        self.manual_je = JournalEntry.objects.create(
            owner=self.owner_a, date=date(2026, 6, 15), reference="MISC-1", status="posted",
        )
        JournalEntryLine.objects.create(
            journal_entry=self.manual_je,
            account=get_rental_income_account(self.owner_a), credit=Decimal("25"),
        )
        self.range_qs = "?start_date=2026-01-01&end_date=2026-12-31"

    @staticmethod
    def _gl_urls(response):
        return [
            t["source_url"]
            for acc in response.context["ledger"]
            for t in acc["transactions"]
            if t["source_url"]
        ]

    def test_general_ledger_links_invoice_expense_repair(self):
        self.client.login(username="xra_owner_a", password=self.password)
        response = self.client.get(reverse("web-general-ledger") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        urls = self._gl_urls(response)
        expected = {
            reverse("web-invoice-detail", args=[self.invoice_a.pk]): ("invoice", self.invoice_a.pk),
            reverse("web-expense-detail", args=[self.expense_a.pk]): ("expense", self.expense_a.pk),
            reverse("web-maintenance-detail", args=[self.repair_a.pk]): ("repair", self.repair_a.pk),
        }
        for url, (context_name, pk) in expected.items():
            self.assertIn(url, urls)
            detail = self.client.get(url)
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.context[context_name].pk, pk)
        manual = [
            t for acc in response.context["ledger"] for t in acc["transactions"]
            if t["source_type"] == "Manual"
        ]
        self.assertTrue(manual)
        self.assertIsNone(manual[0]["source_url"])

    def test_account_ledger_links_invoice_expense_repair(self):
        self.client.login(username="xra_owner_a", password=self.password)
        cases = (
            ("1200", reverse("web-invoice-detail", args=[self.invoice_a.pk])),
            ("5030", reverse("web-expense-detail", args=[self.expense_a.pk])),
            ("5010", reverse("web-maintenance-detail", args=[self.repair_a.pk])),
        )
        for code, url in cases:
            account = Account.objects.get(owner=self.owner_a, code=code)
            ledger = self.client.get(reverse("web-account-ledger", args=[account.pk]) + self.range_qs)
            self.assertEqual(ledger.status_code, 200)
            urls = [t["source_url"] for t in ledger.context["transactions"] if t["source_url"]]
            self.assertIn(url, urls)
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_sales_report_links_own_invoice(self):
        self.client.login(username="xra_owner_a", password=self.password)
        response = self.client.get(reverse("web-sales-report-detail", args=[self.prop_a.pk]) + self.range_qs)
        self.assertEqual(response.status_code, 200)
        items = response.context["items"]
        inv = [i for i in items if i["reference"] == "INV-2026-9501"]
        self.assertEqual(len(inv), 1)
        url = reverse("web-invoice-detail", args=[self.invoice_a.pk])
        self.assertEqual(inv[0]["source_url"], url)
        urls = [i["source_url"] for i in items if i["source_url"]]
        self.assertNotIn(reverse("web-invoice-detail", args=[self.invoice_b.pk]), urls)
        detail = self.client.get(url)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["invoice"].pk, self.invoice_a.pk)

    def test_owner_and_manager_cannot_resolve_owner_b_source_objects(self):
        for username in ("xra_owner_a", "xra_manager_a"):
            self.client.login(username=username, password=self.password)
            self.assertEqual(
                self.client.get(reverse("web-invoice-detail", args=[self.invoice_b.pk])).status_code, 404,
            )
            self.assertEqual(
                self.client.get(reverse("web-expense-detail", args=[self.expense_b.pk])).status_code, 404,
            )
            self.assertEqual(
                self.client.get(reverse("web-maintenance-detail", args=[self.repair_b.pk])).status_code, 404,
            )
            self.client.logout()


class InvoiceDetailNullableAgreementTests(TestCase):
    """Invoice detail renders for every legitimate property/rental-agreement combination."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "invd_owner_a", "+252617000091", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "invd_manager_a", "+252617000092", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "invd_owner_b", "+252617000093", self.password, full_name="Owner B", is_approved=True,
        )
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")
        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Customer A")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Customer B")
        self.agreement_a = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        self.agreement_b = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=self.prop_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("700.00"),
        )

        # All four combinations are legal: both fields are null=True/blank=True.
        self.invoice = Invoice.objects.create(
            owner=self.owner_a, tenant=self.tenant_a, property=self.prop_a,
            rental_agreement=self.agreement_a, invoice_number="INV-2026-9801",
            date=date(2026, 6, 1), due_date=date(2026, 6, 30),
        )
        self.invoice_no_agreement = Invoice.objects.create(
            owner=self.owner_a, tenant=self.tenant_a, property=self.prop_a,
            rental_agreement=None, invoice_number="INV-2026-9802",
            date=date(2026, 6, 1), due_date=date(2026, 6, 30),
        )
        self.invoice_no_property = Invoice.objects.create(
            owner=self.owner_a, tenant=self.tenant_a, property=None,
            rental_agreement=self.agreement_a, invoice_number="INV-2026-9803",
            date=date(2026, 6, 1), due_date=date(2026, 6, 30),
        )
        self.invoice_bare = Invoice.objects.create(
            owner=self.owner_a, tenant=self.tenant_a, property=None,
            rental_agreement=None, invoice_number="INV-2026-9804",
            date=date(2026, 6, 1), due_date=date(2026, 6, 30),
        )
        self.invoice_b = Invoice.objects.create(
            owner=self.owner_b, tenant=self.tenant_b, property=self.prop_b,
            rental_agreement=self.agreement_b, invoice_number="INV-2026-9805",
            date=date(2026, 6, 1), due_date=date(2026, 6, 30),
        )

    def _get_detail(self, invoice):
        self.client.login(username="invd_owner_a", password=self.password)
        return self.client.get(reverse("web-invoice-detail", args=[invoice.pk]))

    def test_detail_renders_with_property_and_null_agreement(self):
        response = self._get_detail(self.invoice_no_agreement)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Court")

    def test_detail_renders_with_property_and_agreement(self):
        response = self._get_detail(self.invoice)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Court")

    def test_detail_renders_with_agreement_and_null_property(self):
        response = self._get_detail(self.invoice_no_property)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Court")

    def test_detail_renders_with_neither_property_nor_agreement(self):
        response = self._get_detail(self.invoice_bare)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Alpha Court")

    def test_ui_created_invoice_without_agreement_renders(self):
        """Full production path: InvoiceCreateView with no agreement -> detail page."""
        self.client.login(username="invd_owner_a", password=self.password)
        response = self.client.post(reverse("web-invoice-create"), {
            "tenant": self.tenant_a.pk,
            "invoice_number": "INV-2026-9899",
            "date": "2026-06-01",
            "due_date": "2026-06-30",
            "status": "draft",
            "notes": "",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-account": "",
            "lines-0-description": "",
            "lines-0-amount": "",
        })
        self.assertEqual(response.status_code, 302)
        created = Invoice.objects.get(invoice_number="INV-2026-9899")
        self.assertIsNone(created.rental_agreement)
        self.assertIsNone(created.property)
        detail = self.client.get(response["Location"])
        self.assertEqual(detail.status_code, 200)

    def test_owner_views_own_invoice(self):
        self.client.login(username="invd_owner_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-invoice-detail", args=[self.invoice.pk])).status_code, 200,
        )

    def test_manager_views_owner_a_invoice(self):
        self.client.login(username="invd_manager_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-invoice-detail", args=[self.invoice.pk])).status_code, 200,
        )

    def test_owner_cannot_view_owner_b_invoice(self):
        self.client.login(username="invd_owner_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-invoice-detail", args=[self.invoice_b.pk])).status_code, 404,
        )

    def test_manager_cannot_view_owner_b_invoice(self):
        self.client.login(username="invd_manager_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-invoice-detail", args=[self.invoice_b.pk])).status_code, 404,
        )


class PaymentNullableAgreementPropertyTests(TestCase):
    """Payment list and dashboard render for agreements with and without a property."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "pna_owner_a", "+252617000101", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "pna_manager_a", "+252617000102", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "pna_owner_b", "+252617000103", self.password, full_name="Owner B", is_approved=True,
        )
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")
        self.unit_a = Unit.objects.create(property=self.prop_a, unit_number="1A")
        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Customer A")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Customer B")
        self.agreement_a_prop = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        # Legitimate state: property NULL while unit is set satisfies agreement_has_rentable_space.
        self.agreement_a_unit = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=None, unit=self.unit_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("300.00"),
        )
        self.agreement_b = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=self.prop_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        self.payment_a_prop = Payment.objects.create(
            rental_agreement=self.agreement_a_prop, amount=Decimal("100.00"), payment_date=date(2026, 6, 1),
        )
        self.payment_a_unit = Payment.objects.create(
            rental_agreement=self.agreement_a_unit, amount=Decimal("200.00"), payment_date=date(2026, 6, 2),
        )
        self.payment_b = Payment.objects.create(
            rental_agreement=self.agreement_b, amount=Decimal("300.00"), payment_date=date(2026, 6, 3),
        )

    def test_payment_list_renders_with_property(self):
        self.client.login(username="pna_owner_a", password=self.password)
        response = self.client.get(reverse("web-payments"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Court")

    def test_payment_list_renders_with_null_property_agreement(self):
        self.client.login(username="pna_owner_a", password=self.password)
        response = self.client.get(reverse("web-payments"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "200.00")

    def test_dashboard_renders_with_property(self):
        self.client.login(username="pna_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Court")

    def test_dashboard_renders_with_null_property_agreement(self):
        self.client.login(username="pna_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "200.00")

    def test_owner_sees_only_own_payment_data(self):
        self.client.login(username="pna_owner_a", password=self.password)
        response = self.client.get(reverse("web-payments"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer A")
        self.assertNotContains(response, "Customer B")
        self.assertNotContains(response, "300.00")
        self.assertEqual(
            self.client.get(reverse("web-payment-detail", args=[self.payment_b.pk])).status_code, 404,
        )

    def test_manager_sees_owner_a_payment_data(self):
        self.client.login(username="pna_manager_a", password=self.password)
        response = self.client.get(reverse("web-payments"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer A")
        self.assertNotContains(response, "Customer B")
        self.assertEqual(
            self.client.get(reverse("web-payment-detail", args=[self.payment_a_prop.pk])).status_code, 200,
        )

    def test_manager_cannot_see_owner_b_payment_data(self):
        self.client.login(username="pna_manager_a", password=self.password)
        response = self.client.get(reverse("web-payments"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Customer B")
        self.assertEqual(
            self.client.get(reverse("web-payment-detail", args=[self.payment_b.pk])).status_code, 404,
        )


class PaymentDetailNullablePropertyTests(TestCase):
    """Payment detail renders for agreements with and without a property, under ownership rules."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "pdn_owner_a", "+252617000121", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "pdn_manager_a", "+252617000122", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "pdn_owner_b", "+252617000123", self.password, full_name="Owner B", is_approved=True,
        )
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")
        self.unit_a = Unit.objects.create(property=self.prop_a, unit_number="1A")
        self.unit_b = Unit.objects.create(property=self.prop_b, unit_number="1B")
        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Customer A")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Customer B")
        self.agreement_a_prop = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        # Legitimate state: property NULL while unit is set satisfies agreement_has_rentable_space.
        self.agreement_a_unit = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=None, unit=self.unit_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("300.00"),
        )
        self.agreement_b_prop = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=self.prop_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        self.agreement_b_unit = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=None, unit=self.unit_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("300.00"),
        )
        self.payment_a_prop = Payment.objects.create(
            rental_agreement=self.agreement_a_prop, amount=Decimal("100.00"), payment_date=date(2026, 6, 1),
        )
        self.payment_a_unit = Payment.objects.create(
            rental_agreement=self.agreement_a_unit, amount=Decimal("200.00"), payment_date=date(2026, 6, 2),
        )
        self.payment_b_prop = Payment.objects.create(
            rental_agreement=self.agreement_b_prop, amount=Decimal("300.00"), payment_date=date(2026, 6, 3),
        )
        self.payment_b_unit = Payment.objects.create(
            rental_agreement=self.agreement_b_unit, amount=Decimal("400.00"), payment_date=date(2026, 6, 4),
        )

    def test_owner_opens_payment_detail_with_property(self):
        self.client.login(username="pdn_owner_a", password=self.password)
        response = self.client.get(reverse("web-payment-detail", args=[self.payment_a_prop.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Court")
        self.assertContains(response, f"/guryaha/{self.prop_a.pk}/")

    def test_owner_opens_payment_detail_with_null_property(self):
        self.client.login(username="pdn_owner_a", password=self.password)
        response = self.client.get(reverse("web-payment-detail", args=[self.payment_a_unit.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "200.00")
        self.assertContains(response, "-")
        self.assertNotContains(response, f"/guryaha/{self.prop_a.pk}/")

    def test_owner_cannot_open_owner_b_payment_detail(self):
        self.client.login(username="pdn_owner_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-payment-detail", args=[self.payment_b_prop.pk])).status_code, 404,
        )

    def test_owner_cannot_open_owner_b_null_property_payment(self):
        self.client.login(username="pdn_owner_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-payment-detail", args=[self.payment_b_unit.pk])).status_code, 404,
        )

    def test_manager_opens_owner_a_null_property_payment_detail(self):
        self.client.login(username="pdn_manager_a", password=self.password)
        response = self.client.get(reverse("web-payment-detail", args=[self.payment_a_unit.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "200.00")

    def test_manager_cannot_open_owner_b_null_property_payment_detail(self):
        self.client.login(username="pdn_manager_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-payment-detail", args=[self.payment_b_unit.pk])).status_code, 404,
        )


class TenantDetailNullablePropertyTests(TestCase):
    """Tenant detail renders for agreements with and without a property, under ownership rules."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "tdn_owner_a", "+252617000131", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "tdn_manager_a", "+252617000132", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "tdn_owner_b", "+252617000133", self.password, full_name="Owner B", is_approved=True,
        )
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")
        self.unit_a = Unit.objects.create(property=self.prop_a, unit_number="1A")
        self.unit_b = Unit.objects.create(property=self.prop_b, unit_number="1B")
        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Customer A")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Customer B")
        self.agreement_a_prop = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        # Legitimate state: property NULL while unit is set satisfies agreement_has_rentable_space.
        self.agreement_a_unit = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=None, unit=self.unit_a, start_date=date(2026, 2, 1),
            monthly_rent=Decimal("300.00"),
        )
        self.agreement_b_unit = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=None, unit=self.unit_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("300.00"),
        )
        # Payment exists so the (currently non-resolving) Payment History loop is exercised.
        self.payment_a_unit = Payment.objects.create(
            rental_agreement=self.agreement_a_unit, amount=Decimal("150.00"), payment_date=date(2026, 6, 1),
        )

    def test_owner_opens_tenant_detail_with_property_agreement(self):
        self.client.login(username="tdn_owner_a", password=self.password)
        response = self.client.get(reverse("web-tenant-detail", args=[self.tenant_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Court")
        self.assertContains(response, f"/guryaha/{self.prop_a.pk}/")

    def test_owner_opens_tenant_detail_with_propertyless_agreement(self):
        self.client.login(username="tdn_owner_a", password=self.password)
        response = self.client.get(reverse("web-tenant-detail", args=[self.tenant_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer A")
        self.assertContains(response, "300.00")
        self.assertContains(response, "1A")
        self.assertContains(response, "-")

    def test_owner_cannot_open_owner_b_tenant_detail(self):
        self.client.login(username="tdn_owner_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-tenant-detail", args=[self.tenant_b.pk])).status_code, 404,
        )

    def test_manager_opens_owner_a_tenant_detail(self):
        self.client.login(username="tdn_manager_a", password=self.password)
        response = self.client.get(reverse("web-tenant-detail", args=[self.tenant_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer A")

    def test_manager_cannot_open_owner_b_tenant_detail(self):
        self.client.login(username="tdn_manager_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-tenant-detail", args=[self.tenant_b.pk])).status_code, 404,
        )


class TenantDetailPaymentHistoryTests(TestCase):
    """Tenant detail Payment History renders payments through RentalAgreement -> Tenant, safely."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "tdh_owner_a", "+252617000141", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "tdh_manager_a", "+252617000142", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "tdh_owner_b", "+252617000143", self.password, full_name="Owner B", is_approved=True,
        )
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")
        self.unit_a = Unit.objects.create(property=self.prop_a, unit_number="1A")
        self.unit_b = Unit.objects.create(property=self.prop_b, unit_number="1B")
        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Customer A")
        self.tenant_single = Tenant.objects.create(owner=self.owner_a, full_name="Single Payor")
        self.tenant_empty = Tenant.objects.create(owner=self.owner_a, full_name="Empty Tenant")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Customer B")

        self.agreement_a_prop = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        self.agreement_a_unit = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=None, unit=self.unit_a, start_date=date(2026, 2, 1),
            monthly_rent=Decimal("300.00"),
        )
        self.agreement_single = RentalAgreement.objects.create(
            tenant=self.tenant_single, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        self.agreement_b = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=self.prop_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )

        self.payment_a_prop = Payment.objects.create(
            rental_agreement=self.agreement_a_prop, amount=Decimal("100.00"),
            payment_date=date(2026, 6, 1), reference_number="REF-A1",
        )
        self.payment_a_unit = Payment.objects.create(
            rental_agreement=self.agreement_a_unit, amount=Decimal("200.00"),
            payment_date=date(2026, 6, 2), reference_number="REF-A2",
        )
        self.payment_single = Payment.objects.create(
            rental_agreement=self.agreement_single, amount=Decimal("50.00"),
            payment_date=date(2026, 5, 15), reference_number="REF-S1",
        )
        self.payment_b = Payment.objects.create(
            rental_agreement=self.agreement_b, amount=Decimal("999.00"),
            payment_date=date(2026, 6, 3), reference_number="REF-B9",
        )

    def test_payment_history_shows_single_payment(self):
        self.client.login(username="tdh_owner_a", password=self.password)
        response = self.client.get(reverse("web-tenant-detail", args=[self.tenant_single.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "50.00")
        self.assertContains(response, "REF-S1")
        self.assertEqual(len(response.context["payments"]), 1)

    def test_payment_history_shows_multiple_payments(self):
        self.client.login(username="tdh_owner_a", password=self.password)
        response = self.client.get(reverse("web-tenant-detail", args=[self.tenant_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100.00")
        self.assertContains(response, "200.00")
        self.assertContains(response, "REF-A1")
        self.assertContains(response, "REF-A2")
        self.assertEqual(len(response.context["payments"]), 2)

    def test_payment_history_shows_empty_state(self):
        self.client.login(username="tdh_owner_a", password=self.password)
        response = self.client.get(reverse("web-tenant-detail", args=[self.tenant_empty.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No payments yet.")

    def test_property_payment_shows_property_link(self):
        self.client.login(username="tdh_owner_a", password=self.password)
        response = self.client.get(reverse("web-tenant-detail", args=[self.tenant_single.pk]))
        # Agreement row + payment row each link the same property.
        self.assertContains(response, f"/guryaha/{self.prop_a.pk}/", count=2)
        self.assertContains(response, "Alpha Court")

    def test_propertyless_payment_renders_safely(self):
        self.client.login(username="tdh_owner_a", password=self.password)
        response = self.client.get(reverse("web-tenant-detail", args=[self.tenant_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "200.00")
        self.assertContains(response, "REF-A2")
        self.assertContains(response, "-")
        self.assertEqual(len(response.context["payments"]), 2)

    def test_owner_sees_only_own_payment_history(self):
        self.client.login(username="tdh_owner_a", password=self.password)
        response = self.client.get(reverse("web-tenant-detail", args=[self.tenant_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "999.00")
        self.assertNotContains(response, "REF-B9")
        self.assertNotContains(response, "Customer B")
        payment_ids = [p.pk for p in response.context["payments"]]
        self.assertNotIn(self.payment_b.pk, payment_ids)

    def test_manager_sees_owner_a_payment_history(self):
        self.client.login(username="tdh_manager_a", password=self.password)
        response = self.client.get(reverse("web-tenant-detail", args=[self.tenant_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100.00")
        self.assertContains(response, "REF-A1")

    def test_owner_cannot_open_owner_b_tenant_detail(self):
        self.client.login(username="tdh_owner_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-tenant-detail", args=[self.tenant_b.pk])).status_code, 404,
        )

    def test_manager_cannot_open_owner_b_tenant_detail(self):
        self.client.login(username="tdh_manager_a", password=self.password)
        self.assertEqual(
            self.client.get(reverse("web-tenant-detail", args=[self.tenant_b.pk])).status_code, 404,
        )


class DashboardPropertylessPaymentTests(TestCase):
    """Dashboard payment rows show property, unit, or room location information safely."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "dpp_owner_a", "+252617000151", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "dpp_manager_a", "+252617000152", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "dpp_owner_b", "+252617000153", self.password, full_name="Owner B", is_approved=True,
        )
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")
        self.unit_a = Unit.objects.create(property=self.prop_a, unit_number="1A")
        self.room_a = Room.objects.create(
            unit=self.unit_a, room_name="Bed 1", monthly_rent=Decimal("120.00"),
        )
        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Customer A")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Customer B")

        self.agreement_a_prop = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        # Legitimate state: property NULL while unit/room is set satisfies agreement_has_rentable_space.
        self.agreement_a_unit = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=None, unit=self.unit_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("300.00"),
        )
        self.agreement_a_room = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=None, unit=None, room=self.room_a,
            start_date=date(2026, 1, 1), monthly_rent=Decimal("120.00"),
        )
        self.agreement_b = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=self.prop_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )

        self.payment_a_prop = Payment.objects.create(
            rental_agreement=self.agreement_a_prop, amount=Decimal("100.00"), payment_date=date(2026, 6, 1),
        )
        self.payment_a_unit = Payment.objects.create(
            rental_agreement=self.agreement_a_unit, amount=Decimal("200.00"), payment_date=date(2026, 6, 2),
        )
        self.payment_a_room = Payment.objects.create(
            rental_agreement=self.agreement_a_room, amount=Decimal("150.00"), payment_date=date(2026, 6, 3),
        )
        self.payment_b = Payment.objects.create(
            rental_agreement=self.agreement_b, amount=Decimal("999.00"), payment_date=date(2026, 6, 4),
        )

    def test_dashboard_renders_payment_with_property(self):
        self.client.login(username="dpp_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100.00")
        self.assertContains(response, "Alpha Court")

    def test_dashboard_renders_propertyless_unit_payment(self):
        self.client.login(username="dpp_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "200.00")
        self.assertContains(response, "Alpha Court - 1A ·")

    def test_dashboard_renders_room_only_payment(self):
        self.client.login(username="dpp_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "150.00")
        self.assertContains(response, "Bed 1")

    def test_owner_sees_only_own_payment_data_on_dashboard(self):
        self.client.login(username="dpp_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "999.00")
        self.assertNotContains(response, "Customer B")

    def test_manager_sees_owner_a_not_owner_b_payments_on_dashboard(self):
        self.client.login(username="dpp_manager_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100.00")
        self.assertNotContains(response, "999.00")
        self.assertNotContains(response, "Customer B")


class DashboardRentStatusPropertylessTests(TestCase):
    """Dashboard Rent Status rows show property, unit, or room location information safely."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "drs_owner_a", "+252617000161", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "drs_manager_a", "+252617000162", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "drs_owner_b", "+252617000163", self.password, full_name="Owner B", is_approved=True,
        )
        self.prop_a = Property.objects.create(owner=self.owner_a, name="Alpha Court", location="Mogadishu")
        self.prop_b = Property.objects.create(owner=self.owner_b, name="Beta Court", location="Mogadishu")
        self.unit_a = Unit.objects.create(property=self.prop_a, unit_number="1A")
        self.room_a = Room.objects.create(
            unit=self.unit_a, room_name="Bed 1", monthly_rent=Decimal("120.00"),
        )
        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="Customer A")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="Customer B")

        # All three agreements are active: property-based, unit-based (property NULL), room-based (property+unit NULL).
        self.agreement_prop = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        self.agreement_unit = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=None, unit=self.unit_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("300.00"),
        )
        self.agreement_room = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=None, unit=None, room=self.room_a,
            start_date=date(2026, 1, 1), monthly_rent=Decimal("120.00"),
        )
        self.agreement_b = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=self.prop_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )

        today = date.today()
        # Full payment this month -> Paid Full; partial payment this month -> Partial; none -> Not Paid.
        self.payment_prop = Payment.objects.create(
            rental_agreement=self.agreement_prop, amount=Decimal("500.00"), payment_date=today,
        )
        self.payment_unit = Payment.objects.create(
            rental_agreement=self.agreement_unit, amount=Decimal("150.00"), payment_date=today,
        )

    def test_property_agreement_shows_property_in_paid_full(self):
        self.client.login(username="drs_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Court</p>")
        self.assertContains(response, "$500 / $500")
        self.assertEqual(len(response.context["rent_paid_full"]), 1)
        self.assertEqual(
            response.context["rent_paid_full"][0]["agreement"].pk, self.agreement_prop.pk,
        )

    def test_unit_agreement_shows_unit_in_partial(self):
        self.client.login(username="drs_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Court - 1A</p>")
        self.assertContains(response, "$150 / $300")
        self.assertEqual(len(response.context["rent_paid_partial"]), 1)
        self.assertEqual(
            response.context["rent_paid_partial"][0]["agreement"].pk, self.agreement_unit.pk,
        )

    def test_room_agreement_shows_room_in_not_paid(self):
        self.client.login(username="drs_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bed 1</p>")
        self.assertContains(response, "$120 due")
        self.assertEqual(len(response.context["rent_not_paid"]), 1)
        self.assertEqual(
            response.context["rent_not_paid"][0]["agreement"].pk, self.agreement_room.pk,
        )

    def test_dashboard_200_for_propertyless_agreements(self):
        self.client.login(username="drs_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        bucket_pks = {
            item["agreement"].pk
            for key in ("rent_paid_full", "rent_paid_partial", "rent_not_paid")
            for item in response.context[key]
        }
        self.assertEqual(
            bucket_pks, {self.agreement_prop.pk, self.agreement_unit.pk, self.agreement_room.pk},
        )

    def test_owner_sees_only_own_rent_status(self):
        self.client.login(username="drs_owner_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Customer B")
        self.assertNotContains(response, "Beta Court")
        for key in ("rent_paid_full", "rent_paid_partial", "rent_not_paid"):
            for item in response.context[key]:
                self.assertEqual(item["agreement"].tenant.owner_id, self.owner_a.pk)

    def test_manager_sees_owner_a_not_owner_b_rent_status(self):
        self.client.login(username="drs_manager_a", password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Court</p>")
        self.assertNotContains(response, "Customer B")
        self.assertNotContains(response, "Beta Court")
        bucket_pks = {
            item["agreement"].pk
            for key in ("rent_paid_full", "rent_paid_partial", "rent_not_paid")
            for item in response.context[key]
        }
        self.assertNotIn(self.agreement_b.pk, bucket_pks)


class UnpostedJournalEntryReportTests(TestCase):
    """Financial reports must include only status="posted" journal entries."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner = User.objects.create_user(
            "upj_owner", "+252618000061", self.password,
            full_name="Owner Unposted", is_approved=True,
        )
        seed_default_chart_of_accounts(self.owner)
        self.cash = Account.objects.get(owner=self.owner, code="1010")
        self.ar = Account.objects.get(owner=self.owner, code="1200")
        self.ap = Account.objects.get(owner=self.owner, code="2010")
        self.revenue = Account.objects.get(owner=self.owner, code="4010")
        self.expense = Account.objects.get(owner=self.owner, code="5010")
        self.property = Property.objects.create(
            owner=self.owner, name="Unposted Villa", location="Mogadishu",
        )
        self.range_qs = "?start_date=2026-01-01&end_date=2026-12-31"
        self.client.login(username="upj_owner", password=self.password)

    def _entry(self, status, ref, dr_account, cr_account, amount, description,
               dr_property=None, cr_property=None):
        je = JournalEntry.objects.create(
            owner=self.owner, date=date(2026, 6, 15), status=status, reference=ref,
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=dr_account, debit=amount, credit=Decimal("0.00"),
            description="%s dr" % description, property=dr_property,
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=cr_account, debit=Decimal("0.00"), credit=amount,
            description="%s cr" % description, property=cr_property,
        )
        return je

    def _revenue_trio(self, cr_property=None):
        self._entry("posted", "REV-POST", self.cash, self.revenue,
                    Decimal("1000.00"), "Posted revenue", cr_property=cr_property)
        self._entry("draft", "REV-DRAFT", self.cash, self.revenue,
                    Decimal("500.00"), "Draft revenue", cr_property=cr_property)
        self._entry("cancelled", "REV-CANCEL", self.cash, self.revenue,
                    Decimal("700.00"), "Cancelled revenue", cr_property=cr_property)

    def test_income_statement_counts_only_posted(self):
        self._revenue_trio()
        response = self.client.get(reverse("web-income-statement") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_revenue"], Decimal("1000.00"))
        self.assertEqual(response.context["net_income"], Decimal("1000.00"))

    def test_balance_sheet_counts_only_posted(self):
        self._revenue_trio()
        response = self.client.get(reverse("web-balance-sheet") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_assets"], Decimal("1000.00"))
        self.assertEqual(response.context["net_income"], Decimal("1000.00"))
        self.assertTrue(response.context["balance_ok"])

    def test_trial_balance_counts_only_posted(self):
        self._revenue_trio()
        response = self.client.get(reverse("web-trial-balance") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_debit"], Decimal("1000.00"))
        self.assertEqual(response.context["total_credit"], Decimal("1000.00"))
        rows = {r["code"]: r for r in response.context["accounts"]}
        self.assertEqual(rows["1010"]["debit"], Decimal("1000.00"))
        self.assertEqual(rows["4010"]["credit"], Decimal("1000.00"))

    def test_general_ledger_lists_only_posted(self):
        self._revenue_trio()
        response = self.client.get(reverse("web-general-ledger") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Posted revenue")
        self.assertNotContains(response, "Draft revenue")
        self.assertNotContains(response, "Cancelled revenue")

    def test_profit_loss_counts_only_posted(self):
        self._revenue_trio()
        response = self.client.get(reverse("web-profit-loss") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_revenue"], Decimal("1000.00"))
        self.assertEqual(response.context["net_income"], Decimal("1000.00"))

    def test_accounts_receivable_counts_only_posted(self):
        self._entry("posted", "INV-A", self.ar, self.revenue,
                    Decimal("300.00"), "Posted AR")
        self._entry("draft", "INV-B", self.ar, self.revenue,
                    Decimal("150.00"), "Draft AR")
        self._entry("cancelled", "INV-C", self.ar, self.revenue,
                    Decimal("170.00"), "Cancelled AR")
        response = self.client.get(reverse("web-ar") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["outstanding_balance"], Decimal("300.00"))
        self.assertEqual(len(response.context["items"]), 1)

    def test_accounts_payable_counts_only_posted(self):
        self._entry("posted", "EXP-A", self.expense, self.ap,
                    Decimal("400.00"), "Posted AP")
        self._entry("draft", "EXP-B", self.expense, self.ap,
                    Decimal("200.00"), "Draft AP")
        self._entry("cancelled", "EXP-C", self.expense, self.ap,
                    Decimal("100.00"), "Cancelled AP")
        response = self.client.get(reverse("web-ap") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["outstanding_payable"], Decimal("400.00"))
        self.assertEqual(len(response.context["items"]), 1)

    def test_sales_report_counts_only_posted(self):
        self._revenue_trio(cr_property=self.property)
        response = self.client.get(reverse("web-sales-report") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        sales = response.context["sales_data"]
        self.assertEqual(len(sales), 1)
        self.assertEqual(sales[0]["total_revenue"], Decimal("1000.00"))

    def test_sales_report_detail_counts_only_posted(self):
        self._revenue_trio(cr_property=self.property)
        response = self.client.get(
            reverse("web-sales-report-detail", args=[self.property.pk]) + self.range_qs
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], Decimal("1000.00"))
        self.assertEqual(len(response.context["items"]), 1)

    def test_expense_report_counts_only_posted(self):
        self._entry("posted", "EXP-1", self.expense, self.cash,
                    Decimal("250.00"), "Posted expense")
        self._entry("draft", "EXP-2", self.expense, self.cash,
                    Decimal("100.00"), "Draft expense")
        self._entry("cancelled", "EXP-3", self.expense, self.cash,
                    Decimal("150.00"), "Cancelled expense")
        response = self.client.get(reverse("web-expense-report") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        expenses = response.context["expense_data"]
        self.assertEqual(len(expenses), 1)
        self.assertEqual(expenses[0]["total_expense"], Decimal("250.00"))

    def test_expense_report_detail_counts_only_posted(self):
        self._entry("posted", "EXP-1", self.expense, self.cash,
                    Decimal("250.00"), "Posted expense")
        self._entry("draft", "EXP-2", self.expense, self.cash,
                    Decimal("100.00"), "Draft expense")
        self._entry("cancelled", "EXP-3", self.expense, self.cash,
                    Decimal("150.00"), "Cancelled expense")
        response = self.client.get(
            reverse("web-expense-report-detail", args=[self.expense.pk]) + self.range_qs
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], Decimal("250.00"))
        self.assertEqual(len(response.context["items"]), 1)

    def test_cash_flow_counts_only_posted(self):
        self._entry("posted", "CF-IN1", self.cash, self.revenue,
                    Decimal("1000.00"), "Posted inflow")
        self._entry("draft", "CF-IN2", self.cash, self.revenue,
                    Decimal("500.00"), "Draft inflow")
        self._entry("cancelled", "CF-IN3", self.cash, self.revenue,
                    Decimal("700.00"), "Cancelled inflow")
        self._entry("posted", "CF-OUT1", self.expense, self.cash,
                    Decimal("250.00"), "Posted outflow")
        self._entry("draft", "CF-OUT2", self.expense, self.cash,
                    Decimal("100.00"), "Draft outflow")
        response = self.client.get(reverse("web-cash-flow") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cash_in"], Decimal("1000.00"))
        self.assertEqual(response.context["cash_out"], Decimal("250.00"))
        self.assertEqual(response.context["net_cash_flow"], Decimal("750.00"))

    def test_account_ledger_lists_only_posted(self):
        self._revenue_trio()
        response = self.client.get(
            reverse("web-account-ledger", args=[self.cash.pk]) + self.range_qs
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_debit"], Decimal("1000.00"))
        self.assertEqual(response.context["total_credit"], Decimal("0.00"))
        self.assertContains(response, "Posted revenue")
        self.assertNotContains(response, "Draft revenue")
        self.assertNotContains(response, "Cancelled revenue")

    def test_chart_of_accounts_balances_count_only_posted(self):
        self._revenue_trio()
        response = self.client.get(
            reverse("web-chart-of-accounts") + self.range_qs + "&export=csv"
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("1000.00", content)
        self.assertNotIn("2200.00", content)

    def test_dashboard_ar_balance_counts_only_posted(self):
        self._entry("posted", "DASH-AR1", self.ar, self.revenue,
                    Decimal("300.00"), "Posted AR dash")
        self._entry("draft", "DASH-AR2", self.ar, self.revenue,
                    Decimal("150.00"), "Draft AR dash")
        self._entry("cancelled", "DASH-AR3", self.ar, self.revenue,
                    Decimal("170.00"), "Cancelled AR dash")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["ar_balance"], Decimal("300.00"))

    def test_inventory_report_independent_of_journal_status(self):
        PropertyAsset.objects.create(property=self.property, name="Generator", quantity=2)
        self._revenue_trio()
        response = self.client.get(reverse("web-inventory-report"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["assets"]), 1)


class UnpostedEntryReportOwnershipTests(TestCase):
    """Posted-only reporting must stay inside the effective-owner boundary."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "upo_owner_a", "+252618000071", self.password, full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "upo_manager_a", "+252618000072", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "upo_owner_b", "+252618000073", self.password, full_name="Owner B", is_approved=True,
        )
        for user in (self.owner_a, self.owner_b):
            seed_default_chart_of_accounts(user)

        self.rev_a = Account.objects.get(owner=self.owner_a, code="4010")
        self.cash_a = Account.objects.get(owner=self.owner_a, code="1010")
        self.rev_b = Account.objects.get(owner=self.owner_b, code="4010")
        self.cash_b = Account.objects.get(owner=self.owner_b, code="1010")
        self.range_qs = "?start_date=2026-01-01&end_date=2026-12-31"

        self._entry(self.owner_a, self.cash_a, self.rev_a, "posted", Decimal("1000.00"))
        self._entry(self.owner_a, self.cash_a, self.rev_a, "draft", Decimal("500.00"))
        self._entry(self.owner_a, self.cash_a, self.rev_a, "cancelled", Decimal("700.00"))
        self._entry(self.owner_b, self.cash_b, self.rev_b, "posted", Decimal("9999.00"))

    def _entry(self, owner, dr_account, cr_account, status, amount):
        je = JournalEntry.objects.create(owner=owner, date=date(2026, 6, 15), status=status)
        JournalEntryLine.objects.create(
            journal_entry=je, account=dr_account, debit=amount, credit=Decimal("0.00"),
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=cr_account, debit=Decimal("0.00"), credit=amount,
        )

    def _income_statement_revenue(self, username):
        self.client.login(username=username, password=self.password)
        response = self.client.get(reverse("web-income-statement") + self.range_qs)
        self.assertEqual(response.status_code, 200)
        return response.context["total_revenue"]

    def test_owner_a_sees_only_own_posted_revenue(self):
        self.assertEqual(
            self._income_statement_revenue("upo_owner_a"), Decimal("1000.00")
        )

    def test_manager_a_sees_only_owner_a_posted_revenue(self):
        self.assertEqual(
            self._income_statement_revenue("upo_manager_a"), Decimal("1000.00")
        )

    def test_owner_b_sees_only_own_posted_revenue(self):
        self.assertEqual(
            self._income_statement_revenue("upo_owner_b"), Decimal("9999.00")
        )


class SalesExpenseCsvExportTests(TestCase):
    """Sales/Expense CSV exports must render valid CSV of posted-only,
    effective-owner-scoped report data (same data as the HTML reports)."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "csv_owner_a", "+252619000081", self.password,
            full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "csv_manager_a", "+252619000082", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "csv_owner_b", "+252619000083", self.password,
            full_name="Owner B", is_approved=True,
        )
        for user in (self.owner_a, self.owner_b):
            seed_default_chart_of_accounts(user)

        self.prop_a = Property.objects.create(
            owner=self.owner_a, name="CSV Alpha Court", location="Mogadishu",
        )
        self.prop_b = Property.objects.create(
            owner=self.owner_b, name="CSV Beta Court", location="Mogadishu",
        )

        cash_a = Account.objects.get(owner=self.owner_a, code="1010")
        rev_a = Account.objects.get(owner=self.owner_a, code="4010")
        exp_a = Account.objects.get(owner=self.owner_a, code="5010")
        cash_b = Account.objects.get(owner=self.owner_b, code="1010")
        rev_b = Account.objects.get(owner=self.owner_b, code="4010")
        exp_b = Account.objects.get(owner=self.owner_b, code="5010")

        # Owner A: posted / draft / cancelled revenue under prop_a.
        self._entry(self.owner_a, "posted", "SREV-A1", cash_a, rev_a,
                    Decimal("1000.00"), cr_property=self.prop_a)
        self._entry(self.owner_a, "draft", "SREV-A2", cash_a, rev_a,
                    Decimal("500.00"), cr_property=self.prop_a)
        self._entry(self.owner_a, "cancelled", "SREV-A3", cash_a, rev_a,
                    Decimal("700.00"), cr_property=self.prop_a)
        # Owner A: posted / draft / cancelled expense.
        self._entry(self.owner_a, "posted", "SEXP-A1", exp_a, cash_a, Decimal("250.00"))
        self._entry(self.owner_a, "draft", "SEXP-A2", exp_a, cash_a, Decimal("100.00"))
        self._entry(self.owner_a, "cancelled", "SEXP-A3", exp_a, cash_a, Decimal("150.00"))
        # Owner B: posted-only figures (distinct amounts identify the owner).
        self._entry(self.owner_b, "posted", "SREV-B1", cash_b, rev_b,
                    Decimal("9999.00"), cr_property=self.prop_b)
        self._entry(self.owner_b, "posted", "SEXP-B1", exp_b, cash_b, Decimal("888.00"))

        self.sales_url = reverse("web-sales-report") + "?start_date=2026-01-01&end_date=2026-12-31&export=csv"
        self.expense_url = reverse("web-expense-report") + "?start_date=2026-01-01&end_date=2026-12-31&export=csv"

    @staticmethod
    def _entry(owner, status, ref, dr_account, cr_account, amount, cr_property=None):
        je = JournalEntry.objects.create(
            owner=owner, date=date(2026, 6, 15), status=status, reference=ref,
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=dr_account, debit=amount, credit=Decimal("0.00"),
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=cr_account, debit=Decimal("0.00"), credit=amount,
            property=cr_property,
        )

    def _get_csv(self, url, username):
        self.client.login(username=username, password=self.password)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        return response

    # ── Sales CSV ────────────────────────────────────────────────────────────

    def test_sales_csv_success_and_format(self):
        response = self._get_csv(self.sales_url, "csv_owner_a")
        self.assertEqual(
            response["Content-Disposition"], "attachment; filename=sales_report.csv",
        )
        lines = response.content.decode().splitlines()
        self.assertEqual(lines[0], "Property Name,Total Revenue ($)")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("CSV Alpha Court,"))

    def test_sales_csv_contains_only_posted_revenue(self):
        content = self._get_csv(self.sales_url, "csv_owner_a").content.decode()
        self.assertIn("1000.00", content)
        self.assertNotIn("2200.00", content)  # posted+draft+cancelled
        self.assertNotIn("500.00", content)
        self.assertNotIn("700.00", content)

    def test_sales_csv_owner_a_excludes_owner_b(self):
        content = self._get_csv(self.sales_url, "csv_owner_a").content.decode()
        self.assertNotIn("CSV Beta Court", content)
        self.assertNotIn("9999.00", content)

        self.client.logout()
        content_b = self._get_csv(self.sales_url, "csv_owner_b").content.decode()
        self.assertIn("CSV Beta Court", content_b)
        self.assertIn("9999.00", content_b)
        self.assertNotIn("CSV Alpha Court", content_b)
        self.assertNotIn("1000.00", content_b)

    def test_sales_csv_manager_a_sees_owner_a_only(self):
        content = self._get_csv(self.sales_url, "csv_manager_a").content.decode()
        self.assertIn("CSV Alpha Court", content)
        self.assertIn("1000.00", content)
        self.assertNotIn("CSV Beta Court", content)
        self.assertNotIn("9999.00", content)

    # ── Expense CSV ──────────────────────────────────────────────────────────

    def test_expense_csv_success_and_format(self):
        response = self._get_csv(self.expense_url, "csv_owner_a")
        self.assertEqual(
            response["Content-Disposition"], "attachment; filename=expense_report.csv",
        )
        lines = response.content.decode().splitlines()
        self.assertEqual(lines[0], "Account Name,Total Expense ($)")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("Maintenance & Repairs,"))

    def test_expense_csv_contains_only_posted_expense(self):
        content = self._get_csv(self.expense_url, "csv_owner_a").content.decode()
        self.assertIn("250.00", content)
        self.assertNotIn("500.00", content)  # posted+draft+cancelled
        self.assertNotIn("100.00", content)
        self.assertNotIn("150.00", content)

    def test_expense_csv_owner_a_excludes_owner_b(self):
        content = self._get_csv(self.expense_url, "csv_owner_a").content.decode()
        self.assertNotIn("888.00", content)

        self.client.logout()
        content_b = self._get_csv(self.expense_url, "csv_owner_b").content.decode()
        self.assertIn("888.00", content_b)
        self.assertNotIn("250.00", content_b)

    def test_expense_csv_manager_a_sees_owner_a_only(self):
        content = self._get_csv(self.expense_url, "csv_manager_a").content.decode()
        self.assertIn("250.00", content)
        self.assertNotIn("888.00", content)


class BalanceSheetPointInTimeTests(TestCase):
    """Balance Sheet is a snapshot: position as of end_date, including all
    posted activity on or before end_date regardless of start_date."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "bs_owner_a", "+252619000091", self.password,
            full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "bs_manager_a", "+252619000092", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "bs_owner_b", "+252619000093", self.password,
            full_name="Owner B", is_approved=True,
        )
        for user in (self.owner_a, self.owner_b):
            seed_default_chart_of_accounts(user)

        cash_a = Account.objects.get(owner=self.owner_a, code="1010")
        cap_a = Account.objects.get(owner=self.owner_a, code="3010")
        rev_a = Account.objects.get(owner=self.owner_a, code="4010")
        cash_b = Account.objects.get(owner=self.owner_b, code="1010")
        cap_b = Account.objects.get(owner=self.owner_b, code="3010")

        # Before selected start_date (2025-12-15): opening cash + capital.
        self._entry(self.owner_a, "posted", "BS-OPEN", date(2025, 12, 15),
                    cash_a, cap_a, Decimal("1000.00"))
        # Draft/cancelled pre-start entries must never count.
        self._entry(self.owner_a, "draft", "BS-DRAFT", date(2025, 12, 10),
                    cash_a, cap_a, Decimal("700.00"))
        self._entry(self.owner_a, "cancelled", "BS-CANCEL", date(2025, 12, 12),
                    cash_a, cap_a, Decimal("900.00"))
        # During the selected period (2026-03-15): cash + revenue.
        self._entry(self.owner_a, "posted", "BS-INPERIOD", date(2026, 3, 15),
                    cash_a, rev_a, Decimal("500.00"))
        # After selected end_date (2026-07-15): must be excluded.
        self._entry(self.owner_a, "posted", "BS-FUTURE", date(2026, 7, 15),
                    cash_a, rev_a, Decimal("300.00"))
        # Owner B: pre-start position only (distinct amount identifies owner).
        self._entry(self.owner_b, "posted", "BS-B-OPEN", date(2025, 12, 15),
                    cash_b, cap_b, Decimal("4000.00"))

        self.url = reverse("web-balance-sheet") + "?start_date=2026-01-01&end_date=2026-06-30"

    @staticmethod
    def _entry(owner, status, ref, when, dr_account, cr_account, amount):
        je = JournalEntry.objects.create(
            owner=owner, date=when, status=status, reference=ref,
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=dr_account, debit=amount, credit=Decimal("0.00"),
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=cr_account, debit=Decimal("0.00"), credit=amount,
        )

    def _get(self, username):
        self.client.login(username=username, password=self.password)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.context

    def test_position_includes_pre_start_activity(self):
        ctx = self._get("bs_owner_a")
        self.assertEqual(ctx["total_assets"], Decimal("1500.00"))
        self.assertEqual(ctx["total_liabilities"], 0)
        self.assertEqual(ctx["total_equity"], Decimal("1000.00"))
        self.assertEqual(ctx["net_income"], Decimal("500.00"))
        self.assertEqual(
            ctx["liabilities_equity_total"], Decimal("1500.00"),
        )
        self.assertTrue(ctx["balance_ok"])

    def test_post_end_activity_excluded(self):
        ctx = self._get("bs_owner_a")
        self.assertNotEqual(ctx["total_assets"], Decimal("1800.00"))
        self.assertNotEqual(ctx["net_income"], Decimal("800.00"))

    def test_draft_and_cancelled_pre_start_excluded(self):
        ctx = self._get("bs_owner_a")
        self.assertNotEqual(ctx["total_assets"], Decimal("3100.00"))
        self.assertNotEqual(ctx["total_equity"], Decimal("2600.00"))

    def test_owner_b_sees_own_position_only(self):
        ctx = self._get("bs_owner_b")
        self.assertEqual(ctx["total_assets"], Decimal("4000.00"))
        self.assertEqual(ctx["total_equity"], Decimal("4000.00"))
        self.assertNotEqual(ctx["total_assets"], Decimal("1500.00"))

    def test_manager_a_sees_owner_a_position(self):
        ctx = self._get("bs_manager_a")
        self.assertEqual(ctx["total_assets"], Decimal("1500.00"))
        self.assertEqual(ctx["total_equity"], Decimal("1000.00"))
        self.assertNotEqual(ctx["total_assets"], Decimal("4000.00"))

    def test_balance_sheet_csv_uses_same_position_values(self):
        self.client.login(username="bs_owner_a", password=self.password)
        response = self.client.get(self.url + "&export=csv")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Total Assets,1500.00", content)
        self.assertIn("Total Equity,1000.00", content)
        self.assertIn("Net Income,500.00", content)
        self.assertNotIn("Total Assets,500.00", content)


class BalanceSheetInternalConsistencyTests(TestCase):
    """Net Income is cumulative through end_date; assets/liabilities/equity
    must use the same cutoff or valid books show 'Not balanced'."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner = User.objects.create_user(
            "bsc_owner", "+252619000094", self.password,
            full_name="Owner Consistency", is_approved=True,
        )
        seed_default_chart_of_accounts(self.owner)
        ar = Account.objects.get(owner=self.owner, code="1200")
        rev = Account.objects.get(owner=self.owner, code="4010")

        # Pre-start revenue: asset + income both exist at end_date.
        je = JournalEntry.objects.create(
            owner=self.owner, date=date(2025, 12, 20), status="posted",
            reference="BSC-PRE-REV",
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=ar, debit=Decimal("400.00"), credit=Decimal("0.00"),
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=rev, debit=Decimal("0.00"), credit=Decimal("400.00"),
        )

        self.url = reverse("web-balance-sheet") + "?start_date=2026-01-01&end_date=2026-06-30"

    def test_pre_start_revenue_keeps_balance_check_balanced(self):
        self.client.login(username="bsc_owner", password=self.password)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertEqual(ctx["total_assets"], Decimal("400.00"))
        self.assertEqual(ctx["net_income"], Decimal("400.00"))
        self.assertTrue(ctx["balance_ok"])


class DashboardAccountingKpiTests(TestCase):
    """Dashboard net_income and bank_balance are accounting figures and must
    reflect posted Journal Entries (owner-scoped, all-time), not raw
    Finance-model totals."""

    password = "SafePassword123!"

    def setUp(self):
        self.owner_a = User.objects.create_user(
            "kpi_owner_a", "+252619000101", self.password,
            full_name="Owner A", is_approved=True,
        )
        self.manager_a = User.objects.create_user(
            "kpi_manager_a", "+252619000102", self.password, full_name="Manager A",
            is_approved=True, managed_account=self.owner_a,
        )
        self.owner_b = User.objects.create_user(
            "kpi_owner_b", "+252619000103", self.password,
            full_name="Owner B", is_approved=True,
        )
        for user in (self.owner_a, self.owner_b):
            seed_default_chart_of_accounts(user)

        self.prop_a = Property.objects.create(
            owner=self.owner_a, name="KPI Alpha Court", location="Mogadishu",
        )
        self.prop_b = Property.objects.create(
            owner=self.owner_b, name="KPI Beta Court", location="Mogadishu",
        )
        self.tenant_a = Tenant.objects.create(owner=self.owner_a, full_name="KPI Customer A")
        self.tenant_b = Tenant.objects.create(owner=self.owner_b, full_name="KPI Customer B")
        self.agreement_a = RentalAgreement.objects.create(
            tenant=self.tenant_a, property=self.prop_a, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        self.agreement_b = RentalAgreement.objects.create(
            tenant=self.tenant_b, property=self.prop_b, start_date=date(2026, 1, 1),
            monthly_rent=Decimal("500.00"),
        )
        # Mirrors BankAccountCreateView: create bank, then link ledger account.
        self.bank_a = BankAccount.objects.create(
            owner=self.owner_a, bank_name="KPI Bank A", account_number="1001",
            account_name="KPI Checking A",
        )
        link_bank_account_to_ledger(self.bank_a)
        self.bank_b = BankAccount.objects.create(
            owner=self.owner_b, bank_name="KPI Bank B", account_number="1002",
            account_name="KPI Checking B",
        )
        link_bank_account_to_ledger(self.bank_b)

    def _dash(self, username):
        self.client.login(username=username, password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        return response.context

    def _payment(self, agreement, amount, when=None, bank=None):
        return Payment.objects.create(
            rental_agreement=agreement, amount=amount,
            payment_date=when or date(2026, 6, 15), bank_account=bank,
        )

    @staticmethod
    def _set_je_status(payment, status):
        """Flip JE status the way JournalEntryUpdateView's form does (status
        is an editable field), leaving the Finance record live."""
        entry = payment.journal_entry
        entry.status = status
        entry.save(update_fields=["status"])

    def _invoice(self, owner, tenant, prop, agreement, amount, number):
        invoice = Invoice.objects.create(
            owner=owner, tenant=tenant, property=prop, rental_agreement=agreement,
            invoice_number=number, date=date(2026, 6, 1), due_date=date(2026, 6, 30),
        )
        InvoiceLine.objects.create(
            invoice=invoice, account=get_rental_income_account(owner),
            description="Rent", amount=amount,
        )
        post_invoice(invoice)
        return invoice

    # ── net_income ───────────────────────────────────────────────────────────

    def test_net_income_includes_posted_invoice_revenue(self):
        self._invoice(
            self.owner_a, self.tenant_a, self.prop_a, self.agreement_a,
            Decimal("1000.00"), "KPI-INV-1",
        )
        ctx = self._dash("kpi_owner_a")
        self.assertEqual(ctx["net_income"], Decimal("1000.00"))
        self.assertEqual(ctx["ar_balance"], Decimal("1000.00"))

    def test_net_income_excludes_cancelled_payment_journal(self):
        payment = self._payment(self.agreement_a, Decimal("600.00"), bank=self.bank_a)
        self._set_je_status(payment, "cancelled")
        ctx = self._dash("kpi_owner_a")
        self.assertEqual(ctx["net_income"], 0)
        self.assertEqual(ctx["bank_balance"], 0)

    def test_net_income_excludes_draft_payment_journal(self):
        payment = self._payment(self.agreement_a, Decimal("600.00"), bank=self.bank_a)
        self._set_je_status(payment, "draft")
        ctx = self._dash("kpi_owner_a")
        self.assertEqual(ctx["net_income"], 0)
        self.assertEqual(ctx["bank_balance"], 0)

    def test_net_income_matches_paid_flows(self):
        self._payment(self.agreement_a, Decimal("500.00"), bank=self.bank_a)
        GeneralExpense.objects.create(
            property=self.prop_a, title="KPI office", category="office",
            amount=Decimal("200.00"), payment_status="paid",
            bank_account=self.bank_a, expense_date=date(2026, 6, 10),
        )
        ctx = self._dash("kpi_owner_a")
        self.assertEqual(ctx["net_income"], Decimal("300.00"))
        self.assertEqual(ctx["bank_balance"], Decimal("300.00"))

    def test_net_income_includes_earlier_year_activity(self):
        self._payment(self.agreement_a, Decimal("250.00"), when=date(2025, 12, 20))
        ctx = self._dash("kpi_owner_a")
        self.assertEqual(ctx["net_income"], Decimal("250.00"))

    # ── bank_balance ─────────────────────────────────────────────────────────

    def test_cash_balance_ignores_unpaid_expense_and_repair(self):
        self._payment(self.agreement_a, Decimal("1000.00"), bank=self.bank_a)
        GeneralExpense.objects.create(
            property=self.prop_a, title="KPI unpaid bill", category="office",
            amount=Decimal("300.00"), payment_status="unpaid",
            bank_account=self.bank_a, expense_date=date(2026, 6, 10),
        )
        MaintenanceRepair.objects.create(
            property=self.prop_a, title="KPI unpaid repair", description="Leak",
            category="plumbing", repair_cost=Decimal("400.00"),
            payment_status="unpaid", bank_account=self.bank_a,
            reported_date=date(2026, 6, 11),
        )
        ctx = self._dash("kpi_owner_a")
        self.assertEqual(ctx["bank_balance"], Decimal("1000.00"))
        self.assertEqual(ctx["net_income"], Decimal("300.00"))

    def test_cash_balance_subtracts_paid_expense(self):
        self._payment(self.agreement_a, Decimal("1000.00"), bank=self.bank_a)
        GeneralExpense.objects.create(
            property=self.prop_a, title="KPI paid bill", category="office",
            amount=Decimal("300.00"), payment_status="paid",
            bank_account=self.bank_a, expense_date=date(2026, 6, 10),
        )
        ctx = self._dash("kpi_owner_a")
        self.assertEqual(ctx["bank_balance"], Decimal("700.00"))

    def test_cash_balance_includes_payments_without_bank_account(self):
        self._payment(self.agreement_a, Decimal("250.00"))
        ctx = self._dash("kpi_owner_a")
        self.assertEqual(ctx["bank_balance"], Decimal("250.00"))
        self.assertEqual(ctx["net_income"], Decimal("250.00"))

    def test_cash_balance_includes_deactivated_bank_ledger(self):
        self._payment(self.agreement_a, Decimal("700.00"), bank=self.bank_a)
        self.bank_a.is_active = False
        self.bank_a.save(update_fields=["is_active"])
        ctx = self._dash("kpi_owner_a")
        self.assertEqual(ctx["bank_balance"], Decimal("700.00"))

    # ── ownership ────────────────────────────────────────────────────────────

    def test_kpi_ownership_isolation(self):
        self._payment(self.agreement_a, Decimal("100.00"), bank=self.bank_a)
        self._payment(self.agreement_b, Decimal("999.00"), bank=self.bank_b)

        ctx_a = self._dash("kpi_owner_a")
        self.assertEqual(ctx_a["net_income"], Decimal("100.00"))
        self.assertEqual(ctx_a["bank_balance"], Decimal("100.00"))

        ctx_m = self._dash("kpi_manager_a")
        self.assertEqual(ctx_m["net_income"], Decimal("100.00"))
        self.assertEqual(ctx_m["bank_balance"], Decimal("100.00"))

        ctx_b = self._dash("kpi_owner_b")
        self.assertEqual(ctx_b["net_income"], Decimal("999.00"))
        self.assertEqual(ctx_b["bank_balance"], Decimal("999.00"))
