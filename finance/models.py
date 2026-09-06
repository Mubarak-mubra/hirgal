from django.db import models
from django.conf import settings
from properties.models import Property, Unit
from rentals.models import RentalAgreement, Tenant


class BankAccount(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_accounts")
    bank_name = models.CharField("Magaca Bangiga", max_length=100)
    account_number = models.CharField("Lambarka Xisaabta", max_length=50)
    account_name = models.CharField("Magaca Xisaabta", max_length=150)
    linked_account = models.ForeignKey("accounting.Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="linked_bank_accounts", help_text="Xisaabta Accounting-ka ee bangigan")
    notes = models.TextField("Faahfaahin", blank=True)
    is_active = models.BooleanField("Waa shaqeyneysaa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["bank_name"]
        unique_together = ("owner", "account_number")

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"


class Payment(models.Model):
    PAYMENT_METHODS = [("cash", "Lacag caddaan ah"), ("mobile_money", "Mobile Money"), ("bank", "Bangiga"), ("other", "Kale")]

    rental_agreement = models.ForeignKey(RentalAgreement, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="mobile_money")
    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    destination_account = models.ForeignKey("accounting.Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="payments_received", help_text="Xisaabta lacagta lagu shubay")
    invoice = models.ForeignKey("accounting.Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    journal_entry = models.OneToOneField("accounting.JournalEntry", on_delete=models.SET_NULL, null=True, blank=True, related_name="payment_source")
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rental_agreement.tenant.full_name} - {self.amount}"


class MaintenanceRepair(models.Model):
    REPAIR_STATUSES = [("reported", "La soo sheegay"), ("in_progress", "Waa socotaa"), ("fixed", "La hagaajiyay"), ("cancelled", "La baajiyay")]
    REPAIR_CATEGORIES = [("plumbing", "Tuubooyinka"), ("electricity", "Koronto"), ("structure", "Dhismaha"), ("appliance", "Qalab"), ("other", "Kale")]
    PAYMENT_STATUSES = [("unpaid", "Aan la bixin"), ("paid", "La bixiyay")]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="maintenance_repairs")
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_repairs")
    reported_by_tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, null=True, blank=True, related_name="reported_repairs")
    rental_agreement = models.ForeignKey(RentalAgreement, on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_repairs")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=REPAIR_CATEGORIES, default="other")
    status = models.CharField(max_length=20, choices=REPAIR_STATUSES, default="reported")
    repair_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expense_account = models.ForeignKey("accounting.Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_repairs", limit_choices_to={"category": "expense"})
    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_repairs")
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUSES, default="unpaid")
    journal_entry = models.OneToOneField("accounting.JournalEntry", on_delete=models.SET_NULL, null=True, blank=True, related_name="repair_source")
    reported_date = models.DateField()
    fixed_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.title


class GeneralExpense(models.Model):
    PAYMENT_STATUSES = [("unpaid", "Aan la bixin"), ("paid", "La bixiyay")]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="general_expenses")
    title = models.CharField(max_length=150)
    category = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_account = models.ForeignKey("accounting.Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="general_expenses", limit_choices_to={"category": "expense"})
    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="general_expenses")
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUSES, default="unpaid")
    journal_entry = models.OneToOneField("accounting.JournalEntry", on_delete=models.SET_NULL, null=True, blank=True, related_name="general_expense_source")
    expense_date = models.DateField()
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.title} - {self.amount}"


class ChatSession(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField("Title", max_length=200, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} - {self.owner.username}"


class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=[("user", "User"), ("ai", "AI")])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
