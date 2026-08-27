from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from properties.models import Property, Room, Unit


class Tenant(models.Model):
    TENANT_TYPES = [("person", "Qof ama qoys"), ("business", "Ganacsi")]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tenants")
    full_name = models.CharField("Magaca qofka ama qoyska", max_length=150)
    tenant_type = models.CharField(max_length=20, choices=TENANT_TYPES, default="person")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "phone_number"], condition=~Q(phone_number=""), name="unique_tenant_phone_per_owner")]

    def __str__(self):
        return self.full_name


class RentalAgreement(models.Model):
    AGREEMENT_STATUSES = [("active", "Socda"), ("ended", "Dhammaaday"), ("cancelled", "La baajiyay")]
    RENTAL_SCOPES = [("whole_property", "Hantida oo dhan"), ("partial_property", "Qeyb ka mid ah")]

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="rental_agreements")
    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name="rental_agreements", null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, null=True, blank=True, related_name="rental_agreements")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, null=True, blank=True, related_name="rental_agreements")
    rental_scope = models.CharField(max_length=20, choices=RENTAL_SCOPES, default="whole_property")
    rented_space_count = models.PositiveIntegerField(default=1)
    agreed_monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=AGREEMENT_STATUSES, default="active")
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")), name="agreement_end_after_start"),
            models.CheckConstraint(condition=Q(property__isnull=False) | Q(unit__isnull=False) | Q(room__isnull=False), name="agreement_has_rentable_space"),
        ]

    def __str__(self):
        return f"{self.tenant.full_name} - {self.unit}"
