from django.db import models
from django.conf import settings
from properties.models import Property
from rentals.models import Tenant, RentalAgreement

class AccountCategory(models.TextChoices):
    ASSET = 'asset', 'Hanti (Asset) - Wixii aad leedahay'
    LIABILITY = 'liability', 'Deyn (Liability) - Wixii aad iska leedahay'
    EQUITY = 'equity', 'Raasamaal (Equity) - Net-worth-kaaga'
    REVENUE = 'revenue', 'Dakhli (Revenue) - Wixii aad ku heshay'
    EXPENSE = 'expense', 'Kharash (Expense) - Wixii aad ku bixisay'

class Account(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='accounts')
    code = models.CharField('Lambarka', max_length=20)
    name = models.CharField('Magaca Xisaabta', max_length=150)
    category = models.CharField('Qaybta', max_length=20, choices=AccountCategory.choices)
    bank_account = models.ForeignKey('finance.BankAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='accounting_accounts', help_text="Xisoabta Bangiga ee la xiriirta (ikhtiyaari)")
    description = models.TextField('Faahfaahin', blank=True)
    is_active = models.BooleanField('Waa Shaqeyneysaa', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('owner', 'code')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

class JournalEntry(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Qabyo'),
        ('posted', 'La diiwaangeliyay'),
        ('cancelled', 'La baajiyay'),
    ]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='journal_entries')
    date = models.DateField('Taariikhda')
    reference = models.CharField('Tixraac', max_length=100, blank=True)
    description = models.TextField('Faahfaahin', blank=True)
    status = models.CharField('Xaaladda', max_length=20, choices=STATUS_CHOICES, default='draft')
    
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
    description = models.CharField('Faahfaahin', max_length=255, blank=True)
    debit = models.DecimalField('Debit', max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField('Credit', max_digits=12, decimal_places=2, default=0)
    
    # Optional link to property for Property-level Profit & Loss reporting
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_lines')

    def __str__(self):
        return f"{self.account.name}: Dr {self.debit} | Cr {self.credit}"

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Qabyo'),
        ('sent', 'La diray'),
        ('paid', 'La bixiyay'),
        ('cancelled', 'La baajiyay'),
    ]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='invoices')
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name='invoices')
    rental_agreement = models.ForeignKey(RentalAgreement, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    
    invoice_number = models.CharField('Numbarka Biilka', max_length=50, unique=True)
    date = models.DateField('Taariikhda Biilka')
    due_date = models.DateField('Taariikhda Kama Dambaysta ah')
    status = models.CharField('Xaaladda', max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField('Faahfaahin', blank=True)
    
    # The journal entry generated when this invoice is posted
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_total_amount(self):
        return sum(line.amount for line in self.lines.all())

    def __str__(self):
        return f"{self.invoice_number} - {self.tenant.full_name}"

class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='invoice_lines', help_text="Xisaabta Dakhliga (Revenue Account)")
    description = models.CharField('Faahfaahin', max_length=255)
    amount = models.DecimalField('Lacagta', max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.description}"

