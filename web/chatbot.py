import os
import json
import traceback
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import google.generativeai as genai
from django.db.models import Sum
from django.utils import timezone


def get_api_key():
    return os.getenv("API_GEMINI")


# ── Database Exploration Tools (READ-ONLY) ────────────────────────────────────

def _get_user_context(user):
    """Shared queryset shortcuts scoped to the logged-in user."""
    from finance.models import Payment, GeneralExpense, MaintenanceRepair, BankAccount
    from accounting.models import Account, JournalEntryLine, Invoice
    from properties.models import Property
    from rentals.models import Tenant, RentalAgreement

    return {
        "properties": Property.objects.filter(owner=user),
        "tenants": Tenant.objects.filter(owner=user),
        "agreements": RentalAgreement.objects.filter(tenant__owner=user, status="active"),
        "payments": Payment.objects.filter(rental_agreement__tenant__owner=user),
        "expenses": GeneralExpense.objects.filter(property__owner=user),
        "repairs": MaintenanceRepair.objects.filter(property__owner=user),
        "invoices": Invoice.objects.filter(owner=user),
        "accounts": Account.objects.filter(owner=user),
        "bank_accounts": BankAccount.objects.filter(owner=user),
    }


def explore_properties(user):
    """List all properties owned by the user with unit counts."""
    try:
        ctx = _get_user_context(user)
        results = []
        for p in ctx["properties"]:
            results.append({
                "name": p.name,
                "location": p.location,
                "type": p.get_property_type_display(),
                "units": p.units.count(),
            })
        return json.dumps(results, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def explore_tenants(user):
    """List all tenants with their contact info."""
    try:
        ctx = _get_user_context(user)
        results = []
        for t in ctx["tenants"]:
            results.append({
                "name": t.full_name,
                "phone": t.phone_number,
            })
        return json.dumps(results, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def explore_agreements(user):
    """List all active rental agreements."""
    try:
        ctx = _get_user_context(user)
        results = []
        for a in ctx["agreements"]:
            results.append({
                "tenant": a.tenant.full_name,
                "property": a.property.name if a.property else None,
                "unit": a.unit.unit_number if a.unit else None,
                "room": a.room.room_name if a.room else None,
                "monthly_rent": float(a.monthly_rent),
                "start_date": str(a.start_date),
                "end_date": str(a.end_date) if a.end_date else None,
            })
        return json.dumps(results, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def explore_payments(user, limit=20):
    """List recent payments."""
    try:
        ctx = _get_user_context(user)
        results = []
        for p in ctx["payments"].order_by("-payment_date")[:limit]:
            results.append({
                "tenant": p.rental_agreement.tenant.full_name,
                "property": p.rental_agreement.property.name if p.rental_agreement.property else None,
                "amount": float(p.amount),
                "date": str(p.payment_date),
                "method": p.get_payment_method_display(),
            })
        return json.dumps(results, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def explore_expenses(user, limit=20):
    """List recent expenses."""
    try:
        ctx = _get_user_context(user)
        results = []
        for e in ctx["expenses"].order_by("-expense_date")[:limit]:
            results.append({
                "title": e.title,
                "property": e.property.name,
                "amount": float(e.amount),
                "category": e.get_category_display() if hasattr(e, 'get_category_display') else e.category,
                "date": str(e.expense_date),
                "status": e.payment_status,
            })
        return json.dumps(results, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def explore_repairs(user, limit=20):
    """List recent maintenance repairs."""
    try:
        ctx = _get_user_context(user)
        results = []
        for r in ctx["repairs"].order_by("-reported_date")[:limit]:
            results.append({
                "title": r.title,
                "property": r.property.name,
                "cost": float(r.repair_cost),
                "status": r.status,
                "payment_status": r.payment_status,
                "reported_date": str(r.reported_date),
            })
        return json.dumps(results, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def explore_invoices(user, limit=20):
    """List invoices and their payment status."""
    try:
        ctx = _get_user_context(user)
        results = []
        for i in ctx["invoices"].order_by("-date")[:limit]:
            results.append({
                "number": i.invoice_number,
                "tenant": i.tenant.full_name,
                "property": i.property.name if i.property else None,
                "total": float(i.get_total_amount()),
                "status": i.status,
                "date": str(i.date),
                "due_date": str(i.due_date),
            })
        return json.dumps(results, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def explore_financial_summary(user):
    """Get a financial summary: revenue, expenses, net income, AR, AP."""
    try:
        ctx = _get_user_context(user)
        today = timezone.now().date()
        month_start = today.replace(day=1)

        total_revenue = ctx["payments"].aggregate(t=Sum("amount"))["t"] or 0
        total_expenses = ctx["expenses"].aggregate(t=Sum("amount"))["t"] or 0
        total_repairs = ctx["repairs"].aggregate(t=Sum("repair_cost"))["t"] or 0
        month_revenue = ctx["payments"].filter(payment_date__gte=month_start).aggregate(t=Sum("amount"))["t"] or 0
        month_expenses = ctx["expenses"].filter(expense_date__gte=month_start).aggregate(t=Sum("amount"))["t"] or 0

        unpaid_ar = ctx["invoices"].filter(status__in=["draft", "sent"])
        ar_total = sum(inv.get_total_amount() for inv in unpaid_ar)

        from accounting.models import JournalEntryLine
        ap_lines = JournalEntryLine.objects.filter(account__code="2010", journal_entry__status="posted")
        ap_total = ap_lines.aggregate(t=Sum("credit") - Sum("debit"))["t"] or 0

        return json.dumps({
            "total_revenue": float(total_revenue),
            "total_expenses": float(total_expenses),
            "total_repairs": float(total_repairs),
            "net_income": float(total_revenue - total_expenses - total_repairs),
            "month_revenue": float(month_revenue),
            "month_expenses": float(month_expenses),
            "accounts_receivable": float(ar_total),
            "accounts_payable": float(ap_total),
        }, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def explore_bank_accounts(user):
    """List bank accounts and their balances."""
    try:
        ctx = _get_user_context(user)
        results = []
        for b in ctx["bank_accounts"]:
            incoming = b.payments.aggregate(t=Sum("amount"))["t"] or 0
            outgoing_exp = b.general_expenses.aggregate(t=Sum("amount"))["t"] or 0
            outgoing_rep = b.maintenance_repairs.aggregate(t=Sum("repair_cost"))["t"] or 0
            acc_num = b.account_number
            masked = "*" * max(0, len(acc_num) - 4) + acc_num[-4:] if len(acc_num) > 4 else acc_num
            results.append({
                "name": b.bank_name,
                "account": masked,
                "balance": float(incoming - outgoing_exp - outgoing_rep),
            })
        return json.dumps(results, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Tool definitions for Gemini ───────────────────────────────────────────────

TOOLS = [
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="explore_properties",
                description="List all properties owned by the user with their details",
                parameters=genai.protos.Schema(type=genai.protos.Type.OBJECT),
            ),
            genai.protos.FunctionDeclaration(
                name="explore_tenants",
                description="List all tenants with their contact information",
                parameters=genai.protos.Schema(type=genai.protos.Type.OBJECT),
            ),
            genai.protos.FunctionDeclaration(
                name="explore_agreements",
                description="List all active rental agreements with rent amounts and dates",
                parameters=genai.protos.Schema(type=genai.protos.Type.OBJECT),
            ),
            genai.protos.FunctionDeclaration(
                name="explore_payments",
                description="List recent rent payments received from tenants",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"limit": genai.protos.Schema(type=genai.protos.Type.INTEGER, description="Max results to return, default 20")},
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="explore_expenses",
                description="List recent property expenses like utilities, bills, etc.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"limit": genai.protos.Schema(type=genai.protos.Type.INTEGER, description="Max results to return, default 20")},
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="explore_repairs",
                description="List recent maintenance and repair records",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"limit": genai.protos.Schema(type=genai.protos.Type.INTEGER, description="Max results to return, default 20")},
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="explore_invoices",
                description="List invoices and their payment status (draft, sent, paid, cancelled)",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"limit": genai.protos.Schema(type=genai.protos.Type.INTEGER, description="Max results to return, default 20")},
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="explore_financial_summary",
                description="Get financial summary: total revenue, expenses, net income, accounts receivable, accounts payable",
                parameters=genai.protos.Schema(type=genai.protos.Type.OBJECT),
            ),
            genai.protos.FunctionDeclaration(
                name="explore_bank_accounts",
                description="List bank accounts with their balances",
                parameters=genai.protos.Schema(type=genai.protos.Type.OBJECT),
            ),
        ]
    )
]

# ── Tool dispatcher ───────────────────────────────────────────────────────────

TOOL_MAP = {
    "explore_properties": explore_properties,
    "explore_tenants": explore_tenants,
    "explore_agreements": explore_agreements,
    "explore_payments": explore_payments,
    "explore_expenses": explore_expenses,
    "explore_repairs": explore_repairs,
    "explore_invoices": explore_invoices,
    "explore_financial_summary": explore_financial_summary,
    "explore_bank_accounts": explore_bank_accounts,
}


# ── Main AI function ──────────────────────────────────────────────────────────

def ask_ai(user, question):
    """Send a question to Gemini with database exploration tools."""
    api_key = get_api_key()
    if not api_key:
        return "API key not configured. Please set API_GEMINI in your .env file."

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.6-flash", tools=TOOLS)

    system_prompt = """You are a helpful assistant for the Hirgal Kiro rent management system.
You can explore the user's database to answer questions about their properties, tenants, rent payments, expenses, repairs, invoices, and finances.
Use the available tools to query the database whenever you need specific data.
Always answer in the same language the user asks in (English or Somali).
Be concise and direct. Always use tools to get real data — do not make up information.
When the user asks about numbers, totals, or specific records, use the tools to get accurate data.
When you get results from a tool, summarize them clearly. If a tool returns an error, mention it briefly and suggest trying again."""

    chat = model.start_chat(history=[
        genai.protos.Content(role="user", parts=[genai.protos.Part(text=system_prompt)]),
        genai.protos.Content(role="model", parts=[genai.protos.Part(text="Understood. I'll use the database tools to answer questions about the rent management system.")]),
    ])

    try:
        response = chat.send_message(question)

        # Handle function calls in a loop
        max_iterations = 10
        iteration = 0
        while response.candidates and response.candidates[0].content.parts:
            iteration += 1
            if iteration > max_iterations:
                break

            function_calls = [p for p in response.candidates[0].content.parts if p.function_call]
            if not function_calls:
                break

            function_responses = []
            for fc in function_calls:
                fn_name = fc.function_call.name
                fn_args = dict(fc.function_call.args) if fc.function_call.args else {}

                if fn_name in TOOL_MAP:
                    fn = TOOL_MAP[fn_name]
                    if fn_name in ["explore_payments", "explore_expenses", "explore_repairs", "explore_invoices"]:
                        result = fn(user, **fn_args)
                    else:
                        result = fn(user)
                else:
                    result = json.dumps({"error": f"Unknown function: {fn_name}"})

                function_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fn_name,
                            response={"result": result},
                        )
                    )
                )

            response = chat.send_message(function_responses)

        # Extract final text response
        if response.candidates and response.candidates[0].content.parts:
            text_parts = [p.text for p in response.candidates[0].content.parts if hasattr(p, 'text') and p.text]
            if text_parts:
                return "\n".join(text_parts)

        return "I couldn't generate a response. Please try again."

    except Exception as e:
        return f"Sorry, I couldn't process that question. Error: {str(e)}"
