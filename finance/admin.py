from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import GeneralExpense, MaintenanceRepair, Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("rental_agreement", "amount", "payment_date", "payment_method")
    list_filter = ("payment_method", "payment_date")
    search_fields = ("rental_agreement__tenant__full_name", "reference_number")


@admin.register(MaintenanceRepair)
class MaintenanceRepairAdmin(admin.ModelAdmin):
    list_display = ("title", "property", "unit", "status", "repair_cost", "reported_date")
    list_filter = ("status", "category", "reported_date")
    search_fields = ("title", "property__name", "unit__unit_number")


@admin.register(GeneralExpense)
class GeneralExpenseAdmin(admin.ModelAdmin):
    list_display = ("title", "property", "category", "amount", "expense_date")
    list_filter = ("category", "expense_date")
    search_fields = ("title", "property__name")
