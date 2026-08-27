from django.db import models

# Create your models here.
from django.db import models
from properties.models import Property, Unit
from rentals.models import RentalAgreement, Tenant


class Payment(models.Model):
    PAYMENT_METHODS = [("cash", "Lacag caddaan ah"), ("mobile_money", "Mobile Money"), ("bank", "Bangiga"), ("other", "Kale")]

    rental_agreement = models.ForeignKey(RentalAgreement, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="mobile_money")
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rental_agreement.tenant.full_name} - {self.amount}"


class MaintenanceRepair(models.Model):
    REPAIR_STATUSES = [("reported", "La soo sheegay"), ("in_progress", "Waa socotaa"), ("fixed", "La hagaajiyay"), ("cancelled", "La baajiyay")]
    REPAIR_CATEGORIES = [("plumbing", "Tuubooyinka"), ("electricity", "Koronto"), ("structure", "Dhismaha"), ("appliance", "Qalab"), ("other", "Kale")]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="maintenance_repairs")
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_repairs")
    reported_by_tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, null=True, blank=True, related_name="reported_repairs")
    rental_agreement = models.ForeignKey(RentalAgreement, on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_repairs")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=REPAIR_CATEGORIES, default="other")
    status = models.CharField(max_length=20, choices=REPAIR_STATUSES, default="reported")
    repair_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reported_date = models.DateField()
    fixed_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.title


class GeneralExpense(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="general_expenses")
    title = models.CharField(max_length=150)
    category = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_date = models.DateField()
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.title} - {self.amount}"
