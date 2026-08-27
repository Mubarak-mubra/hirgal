from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import RentalAgreement, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "tenant_type", "phone_number", "owner")
    list_filter = ("tenant_type",)
    search_fields = ("full_name", "phone_number", "owner__phone_number")


@admin.register(RentalAgreement)
class RentalAgreementAdmin(admin.ModelAdmin):
    list_display = ("tenant", "property", "rental_scope", "rented_space_count", "agreed_monthly_rent", "start_date", "end_date", "status")
    list_filter = ("status", "start_date", "end_date")
    search_fields = ("tenant__full_name", "property__name", "unit__unit_number")
