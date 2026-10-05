from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from properties.models import Property, PropertyType, Unit
from rentals.models import Tenant, RentalAgreement
from finance.models import BankAccount, Payment, GeneralExpense, MaintenanceRepair
from accounting.models import Account, JournalEntry, JournalEntryLine, Invoice, InvoiceLine
from accounting.services import (
    DEFAULT_COA,
    seed_default_chart_of_accounts,
    get_ar_account,
    get_default_cash_account,
    post_payment,
    post_expense,
    post_repair,
    post_invoice,
)

User = get_user_model()


class DoubleEntryAccountingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", phone_number="252615999999", password="password123")
        seed_default_chart_of_accounts(self.user)
        self.property = Property.objects.create(
            owner=self.user,
            name="Test Villa",
            property_type=PropertyType.objects.create(owner=self.user, name="Home"),
            location="Hodan",
        )
        self.tenant = Tenant.objects.create(
            owner=self.user,
            full_name="Farah Ali",
            phone_number="252615000000",
        )
        self.agreement = RentalAgreement.objects.create(
            tenant=self.tenant,
            property=self.property,
            agreed_monthly_rent=Decimal("500.00"),
            monthly_rent=Decimal("500.00"),
            start_date=timezone.now().date(),
        )

    def test_chart_of_accounts_seeded(self):
        accounts = Account.objects.filter(owner=self.user)
        self.assertGreaterEqual(accounts.count(), 10)

    def test_payment_creates_single_journal_entry(self):
        payment = Payment.objects.create(
            rental_agreement=self.agreement,
            amount=Decimal("500.00"),
            payment_date=timezone.now().date(),
            payment_method="mobile_money",
        )
        self.assertIsNotNone(payment.journal_entry)
        self.assertEqual(JournalEntry.objects.filter(owner=self.user).count(), 1)
        
        lines = payment.journal_entry.lines.all()
        self.assertEqual(lines.count(), 2)
        debit_line = lines.get(debit__gt=0)
        credit_line = lines.get(credit__gt=0)
        self.assertEqual(debit_line.debit, Decimal("500.00"))
        self.assertEqual(credit_line.credit, Decimal("500.00"))

    def test_payment_update_is_idempotent(self):
        payment = Payment.objects.create(
            rental_agreement=self.agreement,
            amount=Decimal("500.00"),
            payment_date=timezone.now().date(),
        )
        initial_entry_id = payment.journal_entry.id
        
        # Update payment amount
        payment.amount = Decimal("600.00")
        payment.save()
        
        payment.refresh_from_db()
        self.assertEqual(payment.journal_entry.id, initial_entry_id)
        self.assertEqual(JournalEntry.objects.filter(owner=self.user).count(), 1)
        
        debit_line = payment.journal_entry.lines.get(debit__gt=0)
        self.assertEqual(debit_line.debit, Decimal("600.00"))

    def test_payment_deletion_cancels_journal_entry(self):
        payment = Payment.objects.create(
            rental_agreement=self.agreement,
            amount=Decimal("300.00"),
            payment_date=timezone.now().date(),
        )
        entry = payment.journal_entry
        payment.delete()
        
        entry.refresh_from_db()
        self.assertEqual(entry.status, "cancelled")

    def test_general_expense_posting(self):
        expense = GeneralExpense.objects.create(
            property=self.property,
            title="Electricity Bill",
            category="utility",
            amount=Decimal("150.00"),
            expense_date=timezone.now().date(),
        )
        self.assertIsNotNone(expense.journal_entry)
        self.assertEqual(expense.journal_entry.status, "posted")
        debit_line = expense.journal_entry.lines.get(debit__gt=0)
        self.assertEqual(debit_line.debit, Decimal("150.00"))

    def test_maintenance_repair_posting(self):
        repair = MaintenanceRepair.objects.create(
            property=self.property,
            title="Roof Leak",
            repair_cost=Decimal("200.00"),
            reported_date=timezone.now().date(),
        )
        self.assertIsNotNone(repair.journal_entry)
        debit_line = repair.journal_entry.lines.get(debit__gt=0)
        self.assertEqual(debit_line.debit, Decimal("200.00"))

    def test_invoice_creation_and_payment_settlement(self):
        invoice = Invoice.objects.create(
            owner=self.user,
            tenant=self.tenant,
            rental_agreement=self.agreement,
            property=self.property,
            invoice_number="INV-1001",
            date=timezone.now().date(),
            due_date=timezone.now().date(),
        )
        revenue_account = Account.objects.get(owner=self.user, code="4010")
        InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            description="Monthly Rent",
            amount=Decimal("500.00"),
        )
        # Trigger invoice post
        post_invoice(invoice)
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.journal_entry)

        # Pay invoice in full
        payment = Payment.objects.create(
            rental_agreement=self.agreement,
            invoice=invoice,
            amount=Decimal("500.00"),
            payment_date=timezone.now().date(),
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "paid")


class ChartOfAccountsOwnershipTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="coa_owner", phone_number="252615000101", password="password123", full_name="Owner")
        self.manager = User.objects.create_user(username="coa_manager", phone_number="252615000102", password="password123", full_name="Manager")
        self.manager.managed_account = self.owner
        self.manager.save()

    def test_owner_seeding_creates_accounts_under_owner(self):
        created = seed_default_chart_of_accounts(self.owner)
        self.assertEqual(created, len(DEFAULT_COA))
        self.assertEqual(Account.objects.filter(owner=self.owner).count(), len(DEFAULT_COA))
        self.assertEqual(Account.objects.filter(owner=self.manager).count(), 0)

    def test_manager_seeding_does_not_create_second_chart(self):
        seed_default_chart_of_accounts(self.owner)
        created = seed_default_chart_of_accounts(self.manager)
        self.assertEqual(created, 0)
        self.assertEqual(Account.objects.filter(owner=self.manager).count(), 0)
        self.assertEqual(Account.objects.filter(owner=self.owner).count(), len(DEFAULT_COA))

    def test_manager_account_lookup_resolves_owner_account(self):
        owner_cash = get_default_cash_account(self.owner)
        owner_ar = get_ar_account(self.owner)
        self.assertEqual(get_default_cash_account(self.manager).pk, owner_cash.pk)
        self.assertEqual(get_ar_account(self.manager).pk, owner_ar.pk)
        self.assertEqual(Account.objects.filter(owner=self.manager).count(), 0)

    def test_owner_lookup_behavior_unchanged(self):
        seed_default_chart_of_accounts(self.owner)
        cash = get_default_cash_account(self.owner)
        self.assertEqual(cash.owner, self.owner)
        self.assertEqual(get_default_cash_account(self.owner).pk, cash.pk)
        self.assertEqual(seed_default_chart_of_accounts(self.owner), 0)
        self.assertEqual(Account.objects.filter(owner=self.owner).count(), len(DEFAULT_COA))
