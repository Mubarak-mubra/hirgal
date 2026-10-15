from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.conf import settings
from properties.models import Property, Unit
from rentals.models import RentalAgreement, Tenant


class BankAccount(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_accounts")
    bank_name = models.CharField("Bank name", max_length=100)
    account_number = models.CharField("Account number", max_length=50)
    account_name = models.CharField("Account name", max_length=150)
    linked_account = models.ForeignKey("accounting.Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="linked_bank_accounts", help_text="Linked accounting ledger account (optional)")
    notes = models.TextField("Notes", blank=True)
    is_active = models.BooleanField("Is active", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["bank_name"]
        unique_together = ("owner", "account_number")

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"


class Payment(models.Model):
    PAYMENT_METHODS = [("cash", "Cash"), ("mobile_money", "Mobile Money"), ("bank", "Bank"), ("other", "Other")]

    rental_agreement = models.ForeignKey(RentalAgreement, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="mobile_money")
    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    destination_account = models.ForeignKey("accounting.Account", on_delete=models.SET_NULL, null=True, blank=True, related_name="payments_received", help_text="Account the payment was deposited into")
    invoice = models.ForeignKey("accounting.Invoice", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    journal_entry = models.OneToOneField("accounting.JournalEntry", on_delete=models.SET_NULL, null=True, blank=True, related_name="payment_source")
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "Payment amount must be greater than zero."

        if self.rental_agreement_id:
            owner_id = self.rental_agreement.tenant.owner_id
            if self.bank_account_id and self.bank_account.owner_id != owner_id:
                errors["bank_account"] = "Bank account belongs to a different owner."
            if self.bank_account_id and self.bank_account.linked_account_id:
                linked_account = self.bank_account.linked_account
                if linked_account.owner_id != owner_id or linked_account.category != "asset":
                    errors["bank_account"] = "Bank account must link to an asset account owned by this user."
            if self.destination_account_id:
                if self.destination_account.owner_id != owner_id:
                    errors["destination_account"] = "Destination account belongs to a different owner."
                elif self.destination_account.category != "asset":
                    errors["destination_account"] = "Destination account must be an asset account."

            if self.invoice_id:
                invoice = self.invoice
                if invoice.owner_id != owner_id:
                    errors["invoice"] = "Invoice belongs to a different owner."
                elif invoice.tenant_id != self.rental_agreement.tenant_id:
                    errors["invoice"] = "Invoice belongs to a different customer."
                elif invoice.rental_agreement_id and invoice.rental_agreement_id != self.rental_agreement_id:
                    errors["invoice"] = "Invoice belongs to a different rental agreement."
                elif invoice.status == "cancelled":
                    errors["invoice"] = "A cancelled invoice cannot receive payments."
                elif self.amount is not None:
                    invoice_total = invoice.get_total_amount()
                    if invoice_total <= 0:
                        errors["invoice"] = "A payment cannot be linked to an invoice with no billable total."
                    else:
                        other_payments = invoice.payments.all()
                        if self.pk:
                            other_payments = other_payments.exclude(pk=self.pk)
                        already_paid = other_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
                        if already_paid + self.amount > invoice_total:
                            errors["amount"] = (
                                "Payment exceeds the invoice's remaining balance. "
                                "Reduce the amount or choose a different invoice."
                            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Serialize payments against the invoice so concurrent entries cannot
        # both consume the same remaining balance. The surrounding transaction
        # also rolls back the source row if its accounting signal fails.
        with transaction.atomic():
            if self.invoice_id:
                invoice_model = self._meta.get_field("invoice").remote_field.model
                self.invoice = invoice_model.objects.select_for_update().get(pk=self.invoice_id)
            self.clean()
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.rental_agreement.tenant.full_name} - {self.amount}"


class MaintenanceRepair(models.Model):
    REPAIR_STATUSES = [("reported", "Reported"), ("in_progress", "In progress"), ("fixed", "Fixed"), ("cancelled", "Cancelled")]
    REPAIR_CATEGORIES = [("plumbing", "Plumbing"), ("electricity", "Electricity"), ("structure", "Structure"), ("appliance", "Appliance"), ("other", "Other")]
    PAYMENT_STATUSES = [("unpaid", "Unpaid"), ("paid", "Paid")]

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
    PAYMENT_STATUSES = [("unpaid", "Unpaid"), ("paid", "Paid")]

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
