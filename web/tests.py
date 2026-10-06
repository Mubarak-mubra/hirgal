import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounting.models import Account, Invoice, JournalEntry, JournalEntryLine
from accounting.services import DEFAULT_COA, seed_default_chart_of_accounts
from finance.models import Payment, GeneralExpense, MaintenanceRepair
from properties.models import Property, PropertyType, Unit
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
