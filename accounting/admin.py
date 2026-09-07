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


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "reference", "status", "owner")
    list_filter = ("status",)
    search_fields = ("reference", "description")
    list_editable = ("status",)
    inlines = [JournalEntryLineInline]


@admin.register(JournalEntryLine)
class JournalEntryLineAdmin(admin.ModelAdmin):
    list_display = ("journal_entry", "account", "description", "debit", "credit")
    list_filter = ("account",)
    search_fields = ("description",)


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 1
    fields = ("account", "description", "amount")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "tenant", "date", "due_date", "status", "owner")
    list_filter = ("status",)
    search_fields = ("invoice_number", "tenant__full_name")
    list_editable = ("status",)
    inlines = [InvoiceLineInline]


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ("invoice", "account", "description", "amount")
    list_filter = ("account",)
    search_fields = ("description",)
