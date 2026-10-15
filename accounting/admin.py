from django.contrib import admin
from .models import Account, JournalEntry, JournalEntryLine, Invoice, InvoiceLine


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "is_system", "is_active", "owner")
    list_filter = ("category", "is_active", "is_system")
    search_fields = ("code", "name")
    list_editable = ("is_active",)
    readonly_fields = ("is_system",)
    ordering = ("code",)


class JournalEntryLineInline(admin.TabularInline):
    model = JournalEntryLine
    extra = 1
    fields = ("account", "description", "debit", "credit", "property")

    def has_add_permission(self, request, obj=None):
        return obj is None or (obj.status == "draft" and not obj.is_source_generated)

    def has_delete_permission(self, request, obj=None):
        return obj is None or (obj.status == "draft" and not obj.is_source_generated)

    def get_readonly_fields(self, request, obj=None):
        if obj and (obj.status != "draft" or obj.is_source_generated):
            return self.fields
        return ()


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "reference", "status", "owner")
    list_filter = ("status",)
    search_fields = ("reference", "description")
    inlines = [JournalEntryLineInline]

    readonly_fields = ("status",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "invoice", "payment_source", "repair_source", "general_expense_source"
        )

    def get_readonly_fields(self, request, obj=None):
        if obj and (obj.status != "draft" or obj.is_source_generated):
            return ("owner", "date", "reference", "description", "status", "tenant")
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return False
        return obj.status == "draft" and not obj.is_source_generated

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


@admin.register(JournalEntryLine)
class JournalEntryLineAdmin(admin.ModelAdmin):
    list_display = ("journal_entry", "account", "description", "debit", "credit")
    list_filter = ("account",)
    search_fields = ("description",)

    def has_add_permission(self, request):
        # Create lines through the journal inline, where draft/source rules apply.
        return False

    def has_change_permission(self, request, obj=None):
        if obj and (obj.journal_entry.status != "draft" or obj.journal_entry.is_source_generated):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and (obj.journal_entry.status != "draft" or obj.journal_entry.is_source_generated):
            return False
        return super().has_delete_permission(request, obj)


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 1
    fields = ("account", "description", "amount")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "tenant", "billing_period", "date", "due_date", "status", "owner")
    list_filter = ("status",)
    search_fields = ("invoice_number", "tenant__full_name")
    inlines = [InvoiceLineInline]


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ("invoice", "account", "description", "amount")
    list_filter = ("account",)
    search_fields = ("description",)
