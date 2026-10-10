from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from properties.models import Property
from rentals.models import Tenant, RentalAgreement
   

class AccountCategory(models.TextChoices):
    ASSET = 'asset', 'Hanti (Asset) - Wixii aad leedahay'
    LIABILITY = 'liability', 'Deyn (Liability) - Wixii lagugu leeyahay'
    EQUITY = 'equity', 'Raasamaal (Equity) - Net-worth-kaaga'
    REVENUE = 'revenue', 'Dakhli (Revenue) - Wixii aad ku heshay'
    EXPENSE = 'expense', 'Kharash (Expense) - Wixii aad ku bixisay'

CODE_RANGES = {
    'asset':     (1000, 1999),
    'liability': (2000, 2999),
    'equity':    (3000, 3999),
    'revenue':   (4000, 4999),
    'expense':   (5000, 5999),
}

class Account(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='accounts')
    code = models.CharField('Code', max_length=20)
    name = models.CharField('Account name', max_length=150)
    category = models.CharField('Category', max_length=20, choices=AccountCategory.choices)
    is_system = models.BooleanField('System account', default=False, help_text="System accounts cannot be deleted")
    bank_account = models.ForeignKey('finance.BankAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='accounting_accounts', help_text="Linked bank account (optional)")
    description = models.TextField('Description', blank=True)
    is_active = models.BooleanField('Is active', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('owner', 'code')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        from django.core.exceptions import ValidationError
        code = self.code
        category = self.category

        if code and category:
            lo, hi = CODE_RANGES.get(category, (0, 0))
            if not (lo <= int(code) <= hi):
                raise ValidationError({
                    'code': f'Code {code} ma habboona {category}. Range-ka: {lo} - {hi}'
                })

        if self.pk and self.is_system:
            orig = Account.objects.get(pk=self.pk)
            errors = {}
            if self.name != orig.name:
                errors['name'] = 'System account ma bedeli karto magaca.'
            if self.category != orig.category:
                errors['category'] = 'System account ma bedeli karto nooca.'
            if errors:
                raise ValidationError(errors)

class JournalEntry(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled'),
    ]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='journal_entries')
    date = models.DateField('Date')
    reference = models.CharField('Reference', max_length=100, blank=True)
    description = models.TextField('Description', blank=True)
    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Optional links for general transaction tagging
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"JE-{self.id} ({self.date})"

class JournalEntryLine(models.Model):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines')
    description = models.CharField('Description', max_length=255, blank=True)
    debit = models.DecimalField('Debit', max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField('Credit', max_digits=12, decimal_places=2, default=0)
    
    # Optional link to property for Property-level Profit & Loss reporting
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_lines')

    def __str__(self):
        return f"{self.account.name}: Dr {self.debit} | Cr {self.credit}"

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='invoices')
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name='invoices')
    rental_agreement = models.ForeignKey(RentalAgreement, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    
    invoice_number = models.CharField('Invoice number', max_length=50)
    date = models.DateField('Invoice date')
    due_date = models.DateField('Due date')
    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField('Notes', blank=True)

    # The journal entry generated when this invoice is posted
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "invoice_number"], name="unique_invoice_number_per_owner"),
        ]

    def get_total_amount(self):
        return sum(line.amount for line in self.lines.all())

    def save(self, *args, **kwargs):
        # save() never runs full_clean(); enforce the cancellation invariant at
        # this boundary so direct ORM writes cannot void posted accounting while
        # payment JEs still credit Accounts Receivable against it.
        if self.status == "cancelled" and self.pk and self.payments.exists():
            raise ValidationError({"status": "Cannot cancel an invoice that has payments."})
        super().save(*args, **kwargs)

    def clean(self):
        """Enforce invoice invariants shared by forms, admin, and services."""
        super().clean()
        errors = {}
        if self.tenant_id and self.owner_id and self.tenant.owner_id != self.owner_id:
            errors["tenant"] = "Customer belongs to a different owner."
        if self.rental_agreement_id and self.tenant_id and self.rental_agreement.tenant_id != self.tenant_id:
            errors["rental_agreement"] = "Rental agreement belongs to a different customer."
        if (
            self.property_id
            and self.rental_agreement_id
            and self.rental_agreement.property_id
            and self.rental_agreement.property_id != self.property_id
        ):
            errors["property"] = "Property does not match the rental agreement."
        if self.status == "cancelled" and self.pk and self.payments.exists():
            errors["status"] = "Cannot cancel an invoice that has payments."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.invoice_number} - {self.tenant.full_name}"

class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='invoice_lines', help_text="Revenue account")
    description = models.CharField('Description', max_length=255)
    amount = models.DecimalField('Lacagta', max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        # save() never runs full_clean(); validate here so invalid lines can
        # never reach the ledger through the post_save -> post_invoice path.
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        """A line must post valid revenue: positive amount, revenue account, owner's account."""
        super().clean()
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "Line amount must be greater than zero."
        if self.account_id:
            if self.account.category != "revenue":
                errors["account"] = "Invoice lines must use a revenue account."
            if self.invoice_id and self.account.owner_id != self.invoice.owner_id:
                errors["account"] = "Account belongs to a different owner."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.description}"

