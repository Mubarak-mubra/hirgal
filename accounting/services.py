import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from .models import Account, AccountCategory, JournalEntry, JournalEntryLine, Invoice


# ── Default Chart of Accounts ────────────────────────────────────────────────

DEFAULT_COA = [
    {"code": "1010", "name": "Cash on Hand", "category": "asset", "description": "Petty cash and physical cash"},
    {"code": "1020", "name": "Bank / Mobile Money", "category": "asset", "description": "Bank accounts and mobile money wallets"},
    {"code": "1200", "name": "Accounts Receivable", "category": "asset", "description": "Lacagta aan kireystayaasha ku leenahay"},
    {"code": "2010", "name": "Accounts Payable", "category": "liability", "description": "Lacagaha cid kale lagu leeyahay"},
    {"code": "2050", "name": "Security Deposits Held", "category": "liability", "description": "Tenant security deposits"},
    {"code": "3010", "name": "Owner's Equity", "category": "equity", "description": "Owner's capital investment"},
    {"code": "3020", "name": "Retained Earnings", "category": "equity", "description": "Accumulated net income"},
    {"code": "4010", "name": "Rental Income", "category": "revenue", "description": "Income from rental properties"},
    {"code": "4020", "name": "Other Income", "category": "revenue", "description": "Late fees and other income"},
    {"code": "5010", "name": "Maintenance & Repairs", "category": "expense", "description": "Property maintenance costs"},
    {"code": "5020", "name": "Utilities", "category": "expense", "description": "Water, electricity, internet bills"},
    {"code": "5030", "name": "General & Administrative", "category": "expense", "description": "Office and admin expenses"},
]


def seed_default_chart_of_accounts(user):
    """Auto-create standard COA for a new user. Returns count of created accounts."""
    created = 0
    for acc_data in DEFAULT_COA:
        _, was_created = Account.objects.get_or_create(
            owner=user,
            code=acc_data["code"],
            defaults={
                "name": acc_data["name"],
                "category": acc_data["category"],
                "description": acc_data["description"],
            }
        )
        if was_created:
            created += 1
    return created


def get_or_create_account(user, code, category, name=None):
    """Get or create an account by code. Creates with default name if missing."""
    try:
        return Account.objects.get(owner=user, code=code)
    except Account.DoesNotExist:
        defaults = {}
        for item in DEFAULT_COA:
            if item["code"] == code:
                defaults = {"name": item["name"], "description": item["description"]}
                break
        if name:
            defaults["name"] = name
        acc = Account.objects.create(owner=user, code=code, category=category, **defaults)
        return acc


# ── Auto-seed BankAccount accounting link ────────────────────────────────────

def link_bank_account_to_ledger(bank_account):
    """
    When a BankAccount is created, auto-create or link an Asset account (1020+)
    in the Chart of Accounts so money flows into the general ledger.
    """
    user = bank_account.owner

    if bank_account.linked_account:
        return bank_account.linked_account

    # Find next available code in 1020-1099 range
    existing_codes = Account.objects.filter(
        owner=user, category="asset", code__gte="1020", code__lt="1100"
    ).values_list("code", flat=True).order_by("code")

    taken = set(existing_codes)
    new_code = "1020"
    for i in range(1020, 1100):
        code_str = str(i)
        if code_str not in taken:
            new_code = code_str
            break

    account = Account.objects.create(
        owner=user,
        code=new_code,
        name=f"{bank_account.bank_name} ({bank_account.account_number})",
        category="asset",
        description=f"Bangiga auto-created: {bank_account.bank_name}",
    )
    bank_account.linked_account = account
    bank_account.save(update_fields=["linked_account"])
    return account


def get_default_cash_account(user):
    """Return the user's Cash on Hand account (1010)."""
    return get_or_create_account(user, "1010", "asset")


def get_default_bank_account(user):
    """Return the user's Bank / Mobile Money account (1020)."""
    return get_or_create_account(user, "1020", "asset")


def get_ar_account(user):
    """Return Accounts Receivable (1200)."""
    return get_or_create_account(user, "1200", "asset")


def get_ap_account(user):
    """Return Accounts Payable (2010)."""
    return get_or_create_account(user, "2010", "liability")


def get_rental_income_account(user):
    """Return Rental Income (4010)."""
    return get_or_create_account(user, "4010", "revenue")


def get_other_income_account(user):
    """Return Other Income (4020)."""
    return get_or_create_account(user, "4020", "revenue")


def get_repair_expense_account(user):
    """Return Maintenance & Repairs (5010)."""
    return get_or_create_account(user, "5010", "expense")


def get_utilities_expense_account(user):
    """Return Utilities (5020)."""
    return get_or_create_account(user, "5020", "expense")


def get_general_expense_account(user):
    """Return General & Admin (5030)."""
    return get_or_create_account(user, "5030", "expense")


def resolve_destination_account(user, payment):
    """
    Determine the debit-side (destination) account for a payment.
    Priority: payment.destination_account > payment.bank_account.linked_account > user's 1020
    """
    if payment.destination_account:
        return payment.destination_account
    if payment.bank_account and payment.bank_account.linked_account:
        return payment.bank_account.linked_account
    return get_default_bank_account(user)


def resolve_credit_account_for_payment(user, payment):
    """
    Determine the credit-side account for a rental payment.
    If linked to an invoice → Accounts Receivable (1200)
    Otherwise → Rental Income (4010)
    """
    if payment.invoice:
        return get_ar_account(user)
    return get_rental_income_account(user)


def resolve_expense_debit_account(user, expense):
    """Determine the debit-side account for a general expense."""
    if expense.expense_account:
        return expense.expense_account
    return get_general_expense_account(user)


def resolve_expense_credit_account(user, expense):
    """Determine the credit-side (bank/cash) account for a general expense."""
    if expense.bank_account and expense.bank_account.linked_account:
        return expense.bank_account.linked_account
    return get_default_cash_account(user)


def resolve_repair_debit_account(user, repair):
    """Determine the debit-side account for a repair expense."""
    if repair.expense_account:
        return repair.expense_account
    return get_repair_expense_account(user)


def resolve_repair_credit_account(user, repair):
    """Determine the credit-side (bank/cash) account for a repair."""
    if repair.bank_account and repair.bank_account.linked_account:
        return repair.bank_account.linked_account
    return get_default_cash_account(user)


# ── Idempotent Double-Entry Journal Creation & Updates ───────────────────────

def _upsert_journal_entry(owner, date, reference, description, lines_data, tenant=None, existing_entry=None):
    """
    Create or update a JournalEntry with lines atomically.
    Idempotent: Replaces lines on existing entries cleanly.
    """
    if existing_entry:
        entry = existing_entry
        entry.owner = owner
        entry.date = date
        entry.reference = reference
        entry.description = description
        entry.status = "posted"
        entry.tenant = tenant
        entry.save()
        entry.lines.all().delete()
    else:
        entry = JournalEntry.objects.create(
            owner=owner,
            date=date,
            reference=reference,
            description=description,
            status="posted",
            tenant=tenant,
        )

    for line in lines_data:
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=line["account"],
            description=line.get("description", ""),
            debit=line["debit"],
            credit=line["credit"],
            property=line.get("property"),
        )
    return entry


@transaction.atomic
def post_payment(payment):
    """
    Auto-post a rental payment to the general ledger (Idempotent).
    Debit: Bank/Cash account (destination)
    Credit: Rental Income (4010) or Accounts Receivable (1200) if invoice linked
    """
    user = payment.rental_agreement.tenant.owner
    amount = Decimal(str(payment.amount))
    prop = payment.rental_agreement.property
    tenant = payment.rental_agreement.tenant

    debit_account = resolve_destination_account(user, payment)
    credit_account = resolve_credit_account_for_payment(user, payment)

    lines_data = [
        {
            "account": debit_account,
            "description": f"Lacag ka timid {tenant.full_name}",
            "debit": amount,
            "credit": Decimal("0"),
            "property": prop,
        },
        {
            "account": credit_account,
            "description": f"Lacag ka timid {tenant.full_name}",
            "debit": Decimal("0"),
            "credit": amount,
            "property": prop,
        },
    ]

    ref = payment.reference_number or f"PAY-{payment.pk or 'NEW'}"
    entry = _upsert_journal_entry(
        owner=user,
        date=payment.payment_date,
        reference=ref,
        description=f"Lacag kirada - {tenant.full_name} - {prop.name if prop else ''}",
        lines_data=lines_data,
        tenant=tenant,
        existing_entry=payment.journal_entry,
    )

    if payment.journal_entry != entry or payment.destination_account != debit_account:
        payment.journal_entry = entry
        if not payment.destination_account and debit_account:
            payment.destination_account = debit_account
        payment.save(update_fields=["journal_entry", "destination_account"])

    # Check if linked invoice is fully paid
    if payment.invoice:
        total_paid = payment.invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        if total_paid >= payment.invoice.get_total_amount():
            payment.invoice.status = "paid"
            payment.invoice.save(update_fields=["status"])

    return entry


@transaction.atomic
def post_expense(expense):
    """
    Auto-post a general expense to the general ledger (Idempotent).
    Debit: Expense account (5030 General Expense or specified)
    Credit: Bank/Cash account (1020/1010) if paid, or Accounts Payable (2010) if unpaid
    """
    user = expense.property.owner
    amount = Decimal(str(expense.amount))
    prop = expense.property

    debit_account = resolve_expense_debit_account(user, expense)

    if getattr(expense, "payment_status", "paid") == "unpaid":
        credit_account = get_ap_account(user)
    else:
        credit_account = resolve_expense_credit_account(user, expense)

    lines_data = [
        {
            "account": debit_account,
            "description": expense.title,
            "debit": amount,
            "credit": Decimal("0"),
            "property": prop,
        },
        {
            "account": credit_account,
            "description": expense.title,
            "debit": Decimal("0"),
            "credit": amount,
            "property": prop,
        },
    ]

    ref = f"EXP-{expense.pk or 'NEW'}"
    entry = _upsert_journal_entry(
        owner=user,
        date=expense.expense_date,
        reference=ref,
        description=f"Kharash - {expense.title} - {prop.name if prop else ''}",
        lines_data=lines_data,
        existing_entry=expense.journal_entry,
    )

    if expense.journal_entry != entry or expense.expense_account != debit_account:
        expense.journal_entry = entry
        if not expense.expense_account and debit_account:
            expense.expense_account = debit_account
        expense.save(update_fields=["journal_entry", "expense_account"])

    return entry


@transaction.atomic
def post_repair(repair):
    """
    Auto-post a maintenance repair to the general ledger (Idempotent).
    Only posts if repair_cost > 0. If repair_cost <= 0, cancels existing entry if present.
    Credit side: Bank/Cash if paid, or Accounts Payable (2010) if unpaid.
    """
    if repair.repair_cost <= 0:
        if repair.journal_entry:
            je = repair.journal_entry
            repair.journal_entry = None
            repair.save(update_fields=["journal_entry"])
            je.status = "cancelled"
            je.save(update_fields=["status"])
        return None

    user = repair.property.owner
    amount = Decimal(str(repair.repair_cost))
    prop = repair.property

    debit_account = resolve_repair_debit_account(user, repair)

    if getattr(repair, "payment_status", "paid") == "unpaid":
        credit_account = get_ap_account(user)
    else:
        credit_account = resolve_repair_credit_account(user, repair)

    lines_data = [
        {
            "account": debit_account,
            "description": f"Dayactir - {repair.title}",
            "debit": amount,
            "credit": Decimal("0"),
            "property": prop,
        },
        {
            "account": credit_account,
            "description": f"Dayactir - {repair.title}",
            "debit": Decimal("0"),
            "credit": amount,
            "property": prop,
        },
    ]

    ref = f"REP-{repair.pk or 'NEW'}"
    entry = _upsert_journal_entry(
        owner=user,
        date=repair.fixed_date or repair.reported_date,
        reference=ref,
        description=f"Dayactir - {repair.title} - {prop.name if prop else ''}",
        lines_data=lines_data,
        existing_entry=repair.journal_entry,
    )

    if repair.journal_entry != entry or repair.expense_account != debit_account:
        repair.journal_entry = entry
        if not repair.expense_account and debit_account:
            repair.expense_account = debit_account
        repair.save(update_fields=["journal_entry", "expense_account"])

    return entry


@transaction.atomic
def post_invoice(invoice):
    """
    Auto-post an Invoice to Accounts Receivable (Idempotent).
    Debit: Accounts Receivable (1200)
    Credit: Rental Income (4010) or specific revenue accounts on lines
    """
    user = invoice.owner
    total_amount = invoice.get_total_amount()
    if total_amount <= 0:
        return None

    ar_account = get_ar_account(user)
    lines_data = []

    # Debit Accounts Receivable
    lines_data.append({
        "account": ar_account,
        "description": f"Biil - {invoice.invoice_number} - {invoice.tenant.full_name}",
        "debit": total_amount,
        "credit": Decimal("0"),
        "property": invoice.property,
    })

    # Credit Revenue per line item
    for line in invoice.lines.all():
        lines_data.append({
            "account": line.account or get_rental_income_account(user),
            "description": line.description,
            "debit": Decimal("0"),
            "credit": line.amount,
            "property": invoice.property,
        })

    ref = invoice.invoice_number
    entry = _upsert_journal_entry(
        owner=user,
        date=invoice.date,
        reference=ref,
        description=f"Biil - {invoice.invoice_number} - {invoice.tenant.full_name}",
        lines_data=lines_data,
        tenant=invoice.tenant,
        existing_entry=invoice.journal_entry,
    )

    if invoice.journal_entry != entry:
        invoice.journal_entry = entry
        invoice.save(update_fields=["journal_entry"])

    return entry


def cancel_journal_entry_for_object(instance):
    """Safely mark linked JournalEntry as cancelled when source object is deleted."""
    if hasattr(instance, "journal_entry") and instance.journal_entry:
        entry = instance.journal_entry
        entry.status = "cancelled"
        entry.save(update_fields=["status"])
