import csv
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse
from django.views import View
from django.db.models import Sum, Q
from django.utils import timezone
import datetime

from accounting.models import Account, AccountCategory, JournalEntryLine
from properties.models import PropertyAsset


def render_csv_response(filename, headers, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f"attachment; filename={filename}.csv"
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response


class AccountingDashboardView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        return render(request, "accounting/accounting_dashboard.html")


class AccountingReportMixin(LoginRequiredMixin):
    login_url = "/login/"

    def _parse_date(self, value):
        if not value:
            return None
        try:
            return datetime.date.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    def get_date_range(self, request):
        start = self._parse_date(request.GET.get("start_date"))
        end = self._parse_date(request.GET.get("end_date"))
        if not start:
            start = datetime.date(datetime.date.today().year, 1, 1)
        if not end:
            end = datetime.date.today()
        return start, end

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user"] = self.request.user.get_data_owner()
        return context


# ── 1. Chart of Accounts ──────────────────────────────────────────────────────

class ChartOfAccountsView(AccountingReportMixin, View):
    def get(self, request):
        accounts = Account.objects.filter(owner=request.user.get_data_owner()).order_by("code")
        category_totals = {}
        rows = []
        for acc in accounts:
            cat = acc.get_category_display()
            if cat not in category_totals:
                category_totals[cat] = {"count": 0, "total_balance": 0}
            category_totals[cat]["count"] += 1
            lines = acc.journal_lines.all()
            dr = lines.aggregate(total=Sum("debit"))["total"] or 0
            cr = lines.aggregate(total=Sum("credit"))["total"] or 0
            balance = (dr - cr) if acc.category in ["asset", "expense"] else (cr - dr)
            category_totals[cat]["total_balance"] += balance
            rows.append([acc.code, acc.name, cat, f"{balance:.2f}"])

        if request.GET.get("export") == "csv":
            return render_csv_response("chart_of_accounts", ["Code", "Account Name", "Category", "Balance ($)"], rows)

        return render(request, "accounting/chart_of_accounts.html", {
            "accounts": accounts,
            "category_totals": category_totals,
        })


# ── 1b. Account Ledger (detail for single account) ───────────────────────────

class AccountLedgerView(AccountingReportMixin, View):
    def get(self, request, pk):
        account = get_object_or_404(Account, pk=pk, owner=request.user.get_data_owner())
        start, end = self.get_date_range(request)
        lines = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
        ).select_related("journal_entry").order_by("journal_entry__date")

        line_data = []
        rows = []
        for l in lines:
            je = l.journal_entry
            source_type = ""
            source_url = ""
            if hasattr(je, "payment_source"):
                p = je.payment_source
                source_type = f"Payment: ${p.amount}"
                source_url = f"/lacag-bixinta/{p.pk}/"
            elif hasattr(je, "general_expense_source"):
                e = je.general_expense_source
                source_type = f"Expense: {e.title}"
                source_url = f"/kharashka/{e.pk}/"
            elif hasattr(je, "repair_source"):
                r = je.repair_source
                source_type = f"Repair: {r.title}"
                source_url = f"/dayactirka/{r.pk}/"
            elif hasattr(je, "invoice"):
                inv = je.invoice
                source_type = f"Invoice: {inv.invoice_number}"
                source_url = f"/xisaabiyadda/biilasha/{inv.pk}/"
            else:
                source_type = "Manual"

            line_data.append({
                "date": je.date,
                "description": l.description,
                "debit": l.debit,
                "credit": l.credit,
                "source_type": source_type,
                "source_url": source_url,
            })
            rows.append([je.date, l.description, source_type, f"{l.debit:.2f}", f"{l.credit:.2f}"])

        total_debit = sum(l["debit"] for l in line_data)
        total_credit = sum(l["credit"] for l in line_data)

        if request.GET.get("export") == "csv":
            return render_csv_response(f"ledger_{account.code}", ["Date", "Description", "Source", "Debit ($)", "Credit ($)"], rows)

        return render(request, "accounting/account_ledger.html", {
            "account": account,
            "transactions": line_data,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "start_date": start,
            "end_date": end,
        })


# ── 2. Income Statement ───────────────────────────────────────────────────────

class IncomeStatementView(AccountingReportMixin, View):
    def get(self, request):
        start, end = self.get_date_range(request)
        revenues = JournalEntryLine.objects.filter(
            journal_entry__owner=request.user.get_data_owner(),
            account__category="revenue",
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
        )
        expenses = JournalEntryLine.objects.filter(
            journal_entry__owner=request.user.get_data_owner(),
            account__category="expense",
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
        )
        total_rev = revenues.aggregate(total=Sum("credit") - Sum("debit"))["total"] or 0
        total_exp = expenses.aggregate(total=Sum("debit") - Sum("credit"))["total"] or 0
        net_income = total_rev - total_exp

        if request.GET.get("export") == "csv":
            rows = [
                ["Date Range", f"{start} to {end}"],
                ["Total Revenue", f"{total_rev:.2f}"],
                ["Total Expenses", f"{total_exp:.2f}"],
                ["Net Income", f"{net_income:.2f}"],
            ]
            return render_csv_response("income_statement", ["Metric", "Amount ($)"], rows)

        return render(request, "accounting/income_statement.html", {
            "total_revenue": total_rev,
            "total_expenses": total_exp,
            "net_income": net_income,
            "start_date": start,
            "end_date": end,
        })


# ── 3. Balance Sheet ──────────────────────────────────────────────────────────

class BalanceSheetView(AccountingReportMixin, View):
    def get(self, request):
        start, end = self.get_date_range(request)

        def _sum_lines(category, s, e):
            lines = JournalEntryLine.objects.filter(
                journal_entry__owner=request.user.get_data_owner(),
                account__category=category,
                journal_entry__date__gte=s,
                journal_entry__date__lte=e,
            )
            dr = lines.aggregate(total=Sum("debit"))["total"] or 0
            cr = lines.aggregate(total=Sum("credit"))["total"] or 0
            return dr - cr if category == "asset" else cr - dr

        total_assets = _sum_lines("asset", start, end)
        total_liabilities = _sum_lines("liability", start, end)
        total_equity = _sum_lines("equity", start, end)

        rev_all = JournalEntryLine.objects.filter(
            journal_entry__owner=request.user.get_data_owner(),
            account__category="revenue",
            journal_entry__date__lte=end,
        )
        exp_all = JournalEntryLine.objects.filter(
            journal_entry__owner=request.user.get_data_owner(),
            account__category="expense",
            journal_entry__date__lte=end,
        )
        total_rev_all = rev_all.aggregate(total=Sum("credit") - Sum("debit"))["total"] or 0
        total_exp_all = exp_all.aggregate(total=Sum("debit") - Sum("credit"))["total"] or 0
        net_income = total_rev_all - total_exp_all

        if request.GET.get("export") == "csv":
            rows = [
                ["Date Range", f"{start} to {end}"],
                ["Total Assets", f"{total_assets:.2f}"],
                ["Total Liabilities", f"{total_liabilities:.2f}"],
                ["Total Equity", f"{total_equity:.2f}"],
                ["Net Income", f"{net_income:.2f}"],
            ]
            return render_csv_response("balance_sheet", ["Category", "Amount ($)"], rows)

        return render(request, "accounting/balance_sheet.html", {
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "net_income": net_income,
            "start_date": start,
            "end_date": end,
        })


# ── 4. Trial Balance ──────────────────────────────────────────────────────────

class TrialBalanceView(AccountingReportMixin, View):
    def get(self, request):
        start, end = self.get_date_range(request)
        accounts = Account.objects.filter(owner=request.user.get_data_owner()).order_by("code")
        data = []
        csv_rows = []
        total_dr = 0
        total_cr = 0
        for acc in accounts:
            lines = acc.journal_lines.filter(
                journal_entry__date__gte=start,
                journal_entry__date__lte=end,
            )
            dr = lines.aggregate(total=Sum("debit"))["total"] or 0
            cr = lines.aggregate(total=Sum("credit"))["total"] or 0
            if acc.category in ["asset", "expense"]:
                balance = dr - cr
            else:
                balance = cr - dr
            if balance != 0:
                debit_val = 0
                credit_val = 0
                if acc.category in ["asset", "expense"]:
                    if balance > 0:
                        debit_val = balance
                    else:
                        credit_val = abs(balance)
                else:
                    if balance > 0:
                        credit_val = balance
                    else:
                        debit_val = abs(balance)

                data.append({"account": acc.name, "code": acc.code, "account_id": acc.id, "debit": debit_val, "credit": credit_val})
                csv_rows.append([acc.code, acc.name, f"{debit_val:.2f}", f"{credit_val:.2f}"])
                total_dr += debit_val
                total_cr += credit_val

        if request.GET.get("export") == "csv":
            csv_rows.append(["TOTAL", "Total Balance", f"{total_dr:.2f}", f"{total_cr:.2f}"])
            return render_csv_response("trial_balance", ["Code", "Account Name", "Debit ($)", "Credit ($)"], csv_rows)

        return render(request, "accounting/trial_balance.html", {
            "accounts": data,
            "total_debit": total_dr,
            "total_credit": total_cr,
            "start_date": start,
            "end_date": end,
        })


# ── 5. General Ledger ─────────────────────────────────────────────────────────

class GeneralLedgerView(AccountingReportMixin, View):
    def get(self, request):
        start, end = self.get_date_range(request)
        accounts = Account.objects.filter(owner=request.user.get_data_owner()).order_by("code")
        ledger = []
        csv_rows = []
        for acc in accounts:
            lines = acc.journal_lines.select_related("journal_entry").filter(
                journal_entry__date__gte=start,
                journal_entry__date__lte=end,
            ).order_by("journal_entry__date")
            line_data = []
            for l in lines:
                je = l.journal_entry
                source_type = ""
                source_url = None
                if hasattr(je, "payment_source"):
                    source_type = f"Payment: ${je.payment_source.amount}"
                    source_url = "/lacag-bixinta/%d/" % je.payment_source.pk
                elif hasattr(je, "general_expense_source"):
                    source_type = f"Expense: {je.general_expense_source.title}"
                    source_url = "/kharashka/%d/" % je.general_expense_source.pk
                elif hasattr(je, "repair_source"):
                    source_type = f"Repair: {je.repair_source.title}"
                    source_url = "/dayactirka/%d/" % je.repair_source.pk
                elif hasattr(je, "invoice"):
                    source_type = f"Invoice: {je.invoice.invoice_number}"
                    source_url = "/xisaabiyadda/biilasha/%d/" % je.invoice.pk
                else:
                    source_type = "Manual"

                line_data.append({
                    "date": je.date,
                    "description": l.description,
                    "debit": l.debit,
                    "credit": l.credit,
                    "source_type": source_type,
                    "source_url": source_url,
                })
                csv_rows.append([acc.code, acc.name, je.date, l.description, source_type, f"{l.debit:.2f}", f"{l.credit:.2f}"])

            if line_data:
                ledger.append({
                    "account_name": acc.name,
                    "account_code": acc.code,
                    "account_id": acc.id,
                    "transactions": line_data,
                    "total_debit": sum(l["debit"] for l in line_data),
                    "total_credit": sum(l["credit"] for l in line_data),
                })

        if request.GET.get("export") == "csv":
            return render_csv_response("general_ledger", ["Account Code", "Account Name", "Date", "Description", "Source", "Debit ($)", "Credit ($)"], csv_rows)

        return render(request, "accounting/general_ledger.html", {
            "ledger": ledger,
            "start_date": start,
            "end_date": end,
        })


# ── 6. Cash Flow Statement ───────────────────────────────────────────────────

class CashFlowStatementView(AccountingReportMixin, View):
    def get(self, request):
        start, end = self.get_date_range(request)
        cash_accounts = Account.objects.filter(
            owner=request.user.get_data_owner(), category="asset"
        ).filter(Q(name__icontains="Cash") | Q(name__icontains="Bank") | Q(code__startswith="10"))
        lines = JournalEntryLine.objects.filter(
            account__in=cash_accounts,
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
        )
        cash_in = lines.aggregate(total=Sum("debit"))["total"] or 0
        cash_out = lines.aggregate(total=Sum("credit"))["total"] or 0
        net_cash_flow = cash_in - cash_out

        if request.GET.get("export") == "csv":
            rows = [
                ["Date Range", f"{start} to {end}"],
                ["Cash Inflow (In)", f"{cash_in:.2f}"],
                ["Cash Outflow (Out)", f"{cash_out:.2f}"],
                ["Net Cash Flow", f"{net_cash_flow:.2f}"],
            ]
            return render_csv_response("cash_flow_statement", ["Metric", "Amount ($)"], rows)

        return render(request, "accounting/cash_flow.html", {
            "cash_in": cash_in,
            "cash_out": cash_out,
            "net_cash_flow": net_cash_flow,
            "start_date": start,
            "end_date": end,
        })


# ── 7. Accounts Receivable ───────────────────────────────────────────────────

class AccountsReceivableView(AccountingReportMixin, View):
    def get(self, request):
        start, end = self.get_date_range(request)
        search_query = request.GET.get("search", "").strip()
        ar_accounts = Account.objects.filter(owner=request.user.get_data_owner(), code="1200")
        lines = JournalEntryLine.objects.filter(
            account__in=ar_accounts,
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
        ).select_related("journal_entry", "journal_entry__tenant").order_by("-journal_entry__date")

        dr = lines.aggregate(total=Sum("debit"))["total"] or 0
        cr = lines.aggregate(total=Sum("credit"))["total"] or 0
        balance = dr - cr

        # Build items list first, then derive tenant breakdown from it
        items = []
        for line in lines:
            ref = line.journal_entry.reference or ""
            source_url = None
            source_label = ref
            je = line.journal_entry

            if ref.startswith("INV-"):
                from accounting.models import Invoice
                try:
                    inv = Invoice.objects.get(invoice_number=ref)
                    source_url = "/xisaabiyadda/biilasha/%d/" % inv.pk
                    source_label = inv.invoice_number
                except Invoice.DoesNotExist:
                    pass
            elif hasattr(je, "payment_source"):
                source_url = "/lacag-bixinta/%d/" % je.payment_source.pk

            items.append({
                "date": je.date,
                "reference": source_label,
                "source_url": source_url,
                "description": line.description,
                "debit": float(line.debit),
                "credit": float(line.credit),
                "tenant": je.tenant,
            })

        # Tenant breakdown from items
        tenant_map = {}
        for item in items:
            t = item["tenant"]
            if not t:
                continue
            tid = t.pk
            if tid not in tenant_map:
                tenant_map[tid] = {"tenant": t, "debit": 0, "credit": 0}
            tenant_map[tid]["debit"] += item["debit"]
            tenant_map[tid]["credit"] += item["credit"]

        tenant_list = []
        for data in tenant_map.values():
            net = data["debit"] - data["credit"]
            tenant_list.append({
                "tenant": data["tenant"],
                "debit": data["debit"],
                "credit": data["credit"],
                "balance": net,
            })
        tenant_list.sort(key=lambda x: abs(x["balance"]), reverse=True)

        if search_query:
            q = search_query.lower()
            tenant_list = [t for t in tenant_list if q in t["tenant"].full_name.lower() or q in (t["tenant"].phone_number or "").lower()]
            items = [i for i in items if i["tenant"] and (q in i["tenant"].full_name.lower() or q in (i["tenant"].phone_number or "").lower())]
        else:
            # Hide fully-paid tenants by default
            tenant_list = [t for t in tenant_list if abs(t["balance"]) > 0.001]

        if request.GET.get("export") == "csv":
            rows = [["Date", "Reference", "Description", "Debit", "Credit"]]
            for item in items:
                rows.append([item["date"], item["reference"], item["description"], item["debit"], item["credit"]])
            rows.append(["", "", "Outstanding Balance", "", balance])
            return render_csv_response("accounts_receivable", rows[0], rows[1:])

        return render(request, "accounting/accounts_receivable.html", {
            "outstanding_balance": balance,
            "start_date": start,
            "end_date": end,
            "items": items,
            "tenant_list": tenant_list,
            "total_debit": float(dr),
            "total_credit": float(cr),
            "search_query": search_query,
        })


# ── 8. Accounts Payable ──────────────────────────────────────────────────────

class AccountsPayableView(AccountingReportMixin, View):
    def get(self, request):
        start, end = self.get_date_range(request)
        search_query = request.GET.get("search", "").strip()
        ap_accounts = Account.objects.filter(owner=request.user.get_data_owner(), code="2010")
        lines = JournalEntryLine.objects.filter(
            account__in=ap_accounts,
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
        ).select_related("journal_entry", "journal_entry__tenant").order_by("-journal_entry__date")

        cr = lines.aggregate(total=Sum("credit"))["total"] or 0
        dr = lines.aggregate(total=Sum("debit"))["total"] or 0
        payable = cr - dr

        # Build items list, resolve source links
        items = []
        for line in lines:
            ref = line.journal_entry.reference or ""
            source_url = None
            source_label = ref
            je = line.journal_entry

            if ref.startswith("EXP-"):
                pk = ref.split("-")[1]
                try:
                    from finance.models import GeneralExpense
                    GeneralExpense.objects.get(pk=pk)
                    source_url = "/kharashka/%s/" % pk
                except GeneralExpense.DoesNotExist:
                    pass
            elif ref.startswith("REP-"):
                pk = ref.split("-")[1]
                try:
                    from finance.models import MaintenanceRepair
                    MaintenanceRepair.objects.get(pk=pk)
                    source_url = "/dayactirka/%s/" % pk
                except MaintenanceRepair.DoesNotExist:
                    pass

            items.append({
                "date": je.date,
                "reference": source_label,
                "source_url": source_url,
                "description": line.description,
                "debit": float(line.debit),
                "credit": float(line.credit),
                "tenant": je.tenant,
            })

        # Vendor/tenant breakdown from items
        vendor_map = {}
        for item in items:
            t = item["tenant"]
            key = t.pk if t else 0
            if key not in vendor_map:
                vendor_map[key] = {"tenant": t, "debit": 0, "credit": 0, "name": t.full_name if t else "Unknown"}
            vendor_map[key]["debit"] += item["debit"]
            vendor_map[key]["credit"] += item["credit"]

        vendor_list = []
        for data in vendor_map.values():
            net = data["credit"] - data["debit"]
            vendor_list.append({
                "tenant": data["tenant"],
                "name": data["name"],
                "debit": data["debit"],
                "credit": data["credit"],
                "balance": net,
            })
        vendor_list.sort(key=lambda x: abs(x["balance"]), reverse=True)

        if search_query:
            q = search_query.lower()
            vendor_list = [v for v in vendor_list if q in v["name"].lower() or (v["tenant"] and q in (getattr(v["tenant"], "phone_number", "") or "").lower())]
            items = [i for i in items if i["tenant"] and (q in i["tenant"].full_name.lower() or q in (getattr(i["tenant"], "phone_number", "") or "").lower())]
        else:
            vendor_list = [v for v in vendor_list if abs(v["balance"]) > 0.001]

        if request.GET.get("export") == "csv":
            rows = [["Date", "Reference", "Description", "Debit", "Credit"]]
            for item in items:
                rows.append([item["date"], item["reference"], item["description"], item["debit"], item["credit"]])
            rows.append(["", "", "Outstanding Payable", "", payable])
            return render_csv_response("accounts_payable", rows[0], rows[1:])

        return render(request, "accounting/accounts_payable.html", {
            "outstanding_payable": payable,
            "start_date": start,
            "end_date": end,
            "items": items,
            "vendor_list": vendor_list,
            "total_debit": float(dr),
            "total_credit": float(cr),
            "search_query": search_query,
        })


# ── 9. Inventory Report ──────────────────────────────────────────────────────

class InventoryReportView(AccountingReportMixin, View):
    def get(self, request):
        assets = PropertyAsset.objects.filter(property__owner=request.user.get_data_owner())
        if request.GET.get("export") == "csv":
            rows = [[a.property.name, a.name, a.quantity, a.get_condition_display(), a.responsible_party or ""] for a in assets]
            return render_csv_response("inventory_report", ["Property", "Asset Name", "Quantity", "Condition", "Responsible Party"], rows)

        return render(request, "accounting/inventory_report.html", {"assets": assets})


# ── 10. Sales Report ─────────────────────────────────────────────────────────

class SalesReportView(AccountingReportMixin, View):
    def get(self, request):
        start, end = self.get_date_range(request)
        revenues = JournalEntryLine.objects.filter(
            journal_entry__owner=request.user.get_data_owner(),
            account__category="revenue",
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
        )
        sales_by_property = revenues.values("property__name", "property_id").annotate(
            total_revenue=Sum("credit") - Sum("debit")
        ).order_by("property__name")
        sales_list = list(sales_by_property)

        if request.GET.get("export") == "csv":
            rows = [[s["property__name"] or "General", f"{s[total_revenue]:.2f}"] for s in sales_list]
            return render_csv_response("sales_report", ["Property Name", "Total Revenue ($)"], rows)

        return render(request, "accounting/sales_report.html", {
            "sales_data": sales_list,
            "start_date": start,
            "end_date": end,
        })


# ── 11. Expense Report ───────────────────────────────────────────────────────

class ExpenseReportView(AccountingReportMixin, View):
    def get(self, request):
        start, end = self.get_date_range(request)
        expenses = JournalEntryLine.objects.filter(
            journal_entry__owner=request.user.get_data_owner(),
            account__category="expense",
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
        )
        expense_by_account = expenses.values("account__name", "account_id").annotate(
            total_expense=Sum("debit") - Sum("credit")
        ).order_by("account__name")
        exp_list = list(expense_by_account)

        if request.GET.get("export") == "csv":
            rows = [[e["account__name"], f"{e[total_expense]:.2f}"] for e in exp_list]
            return render_csv_response("expense_report", ["Account Name", "Total Expense ($)"], rows)

        return render(request, "accounting/expense_report.html", {
            "expense_data": exp_list,
            "start_date": start,
            "end_date": end,
        })


# ── 11b. Sales Report Detail (per property) ─────────────────────────────────

class SalesReportDetailView(AccountingReportMixin, View):
    def get(self, request, property_id):
        start, end = self.get_date_range(request)
        lines = JournalEntryLine.objects.filter(
            journal_entry__owner=request.user.get_data_owner(),
            account__category="revenue",
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
            property_id=property_id,
        ).select_related("journal_entry", "account").order_by("-journal_entry__date")

        total = lines.aggregate(t=Sum("credit") - Sum("debit"))["t"] or 0
        from properties.models import Property
        prop = get_object_or_404(Property, pk=property_id, owner=request.user.get_data_owner())

        items = []
        for line in lines:
            ref = line.journal_entry.reference or ""
            source_url = None
            if ref.startswith("INV-"):
                from accounting.models import Invoice
                try:
                    inv = Invoice.objects.get(invoice_number=ref)
                    source_url = "/xisaabiyadda/biilasha/%d/" % inv.pk
                except Invoice.DoesNotExist:
                    pass
            elif ref.startswith("PAY-"):
                pk = ref.split("-")[-1]
                source_url = "/lacagaha/%s/" % pk

            items.append({
                "date": line.journal_entry.date,
                "reference": ref,
                "source_url": source_url,
                "description": line.description,
                "debit": line.debit,
                "credit": line.credit,
            })

        return render(request, "accounting/sales_report_detail.html", {
            "property": prop,
            "items": items,
            "total": total,
            "start_date": start,
            "end_date": end,
        })


# ── 11c. Expense Report Detail (per account) ────────────────────────────────

class ExpenseReportDetailView(AccountingReportMixin, View):
    def get(self, request, account_id):
        start, end = self.get_date_range(request)
        lines = JournalEntryLine.objects.filter(
            journal_entry__owner=request.user.get_data_owner(),
            account__category="expense",
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
            account_id=account_id,
        ).select_related("journal_entry", "account").order_by("-journal_entry__date")

        total = lines.aggregate(t=Sum("debit") - Sum("credit"))["t"] or 0
        account = get_object_or_404(Account, pk=account_id, owner=request.user.get_data_owner())

        items = []
        for line in lines:
            ref = line.journal_entry.reference or ""
            source_url = None
            if ref.startswith("EXP-"):
                pk = ref.split("-")[1]
                source_url = "/kharashka/%s/" % pk
            elif ref.startswith("REP-"):
                pk = ref.split("-")[1]
                source_url = "/dayactirka/%s/" % pk

            items.append({
                "date": line.journal_entry.date,
                "reference": ref,
                "source_url": source_url,
                "description": line.description,
                "debit": line.debit,
                "credit": line.credit,
            })

        return render(request, "accounting/expense_report_detail.html", {
            "account": account,
            "items": items,
            "total": total,
            "start_date": start,
            "end_date": end,
        })


# ── 12. Profit & Loss Statement ──────────────────────────────────────────────

class ProfitLossView(AccountingReportMixin, View):
    def get(self, request):
        start, end = self.get_date_range(request)
        revenues = JournalEntryLine.objects.filter(
            journal_entry__owner=request.user.get_data_owner(),
            account__category="revenue",
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
        )
        expenses = JournalEntryLine.objects.filter(
            journal_entry__owner=request.user.get_data_owner(),
            account__category="expense",
            journal_entry__date__gte=start,
            journal_entry__date__lte=end,
        )
        total_rev = revenues.aggregate(total=Sum("credit") - Sum("debit"))["total"] or 0
        total_exp = expenses.aggregate(total=Sum("debit") - Sum("credit"))["total"] or 0
        net_income = total_rev - total_exp

        if request.GET.get("export") == "csv":
            rows = [
                ["Date Range", f"{start} to {end}"],
                ["Total Revenue", f"{total_rev:.2f}"],
                ["Total Expenses", f"{total_exp:.2f}"],
                ["Net Income", f"{net_income:.2f}"],
            ]
            return render_csv_response("profit_and_loss", ["Metric", "Amount ($)"], rows)

        return render(request, "accounting/profit_loss.html", {
            "total_revenue": total_rev,
            "total_expenses": total_exp,
            "net_income": net_income,
            "start_date": start,
            "end_date": end,
        })
