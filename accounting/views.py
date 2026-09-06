from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from .models import Account, AccountCategory, JournalEntryLine

class ChartOfAccountsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        accounts = Account.objects.filter(owner=owner)
        data = [{'code': a.code, 'name': a.name, 'category': a.get_category_display()} for a in accounts]
        return Response({'report': 'Chart of Accounts', 'data': data})

class IncomeStatementView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        revenues = JournalEntryLine.objects.filter(journal_entry__owner=owner, account__category=AccountCategory.REVENUE)
        expenses = JournalEntryLine.objects.filter(journal_entry__owner=owner, account__category=AccountCategory.EXPENSE)
        
        total_rev = revenues.aggregate(total=Sum('credit') - Sum('debit'))['total'] or 0
        total_exp = expenses.aggregate(total=Sum('debit') - Sum('credit'))['total'] or 0
        
        return Response({
            'report': 'Income Statement (Profit & Loss)',
            'revenue': total_rev,
            'expenses': total_exp,
            'net_income': total_rev - total_exp
        })

class BalanceSheetView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        assets = JournalEntryLine.objects.filter(journal_entry__owner=owner, account__category=AccountCategory.ASSET)
        liabilities = JournalEntryLine.objects.filter(journal_entry__owner=owner, account__category=AccountCategory.LIABILITY)
        equity = JournalEntryLine.objects.filter(journal_entry__owner=owner, account__category=AccountCategory.EQUITY)
        
        total_assets = assets.aggregate(total=Sum('debit') - Sum('credit'))['total'] or 0
        total_liab = liabilities.aggregate(total=Sum('credit') - Sum('debit'))['total'] or 0
        total_equity = equity.aggregate(total=Sum('credit') - Sum('debit'))['total'] or 0
        
        return Response({
            'report': 'Balance Sheet',
            'assets': total_assets,
            'liabilities': total_liab,
            'equity': total_equity
        })

class TrialBalanceView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        accounts = Account.objects.filter(owner=owner)
        data = []
        total_dr = 0
        total_cr = 0
        for acc in accounts:
            lines = acc.journal_lines.all()
            dr = lines.aggregate(total=Sum('debit'))['total'] or 0
            cr = lines.aggregate(total=Sum('credit'))['total'] or 0
            
            balance = 0
            if acc.category in [AccountCategory.ASSET, AccountCategory.EXPENSE]:
                balance = dr - cr
                if balance > 0:
                    data.append({'account': acc.name, 'debit': balance, 'credit': 0})
                    total_dr += balance
                elif balance < 0:
                    data.append({'account': acc.name, 'debit': 0, 'credit': abs(balance)})
                    total_cr += abs(balance)
            else:
                balance = cr - dr
                if balance > 0:
                    data.append({'account': acc.name, 'debit': 0, 'credit': balance})
                    total_cr += balance
                elif balance < 0:
                    data.append({'account': acc.name, 'debit': abs(balance), 'credit': 0})
                    total_dr += abs(balance)
                    
        return Response({
            'report': 'Trial Balance',
            'accounts': data,
            'total_debit': total_dr,
            'total_credit': total_cr
        })

class GeneralLedgerView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        accounts = Account.objects.filter(owner=owner)
        ledger = []
        for acc in accounts:
            lines = acc.journal_lines.select_related('journal_entry').order_by('journal_entry__date')
            line_data = [{'date': l.journal_entry.date, 'description': l.description, 'debit': l.debit, 'credit': l.credit} for l in lines]
            if line_data:
                ledger.append({
                    'account_name': acc.name,
                    'account_code': acc.code,
                    'transactions': line_data
                })
        return Response({'report': 'General Ledger', 'ledger': ledger})

class AccountsReceivableReportView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        ar_accounts = Account.objects.filter(owner=owner, code='1200')
        lines = JournalEntryLine.objects.filter(account__in=ar_accounts)
        
        dr = lines.aggregate(total=Sum('debit'))['total'] or 0
        cr = lines.aggregate(total=Sum('credit'))['total'] or 0
        balance = dr - cr
        
        return Response({
            'report': 'Accounts Receivable Report',
            'outstanding_balance': balance
        })

class AccountsPayableReportView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        ap_accounts = Account.objects.filter(owner=owner, code='2010')
        lines = JournalEntryLine.objects.filter(account__in=ap_accounts)
        cr = lines.aggregate(total=Sum('credit'))['total'] or 0
        dr = lines.aggregate(total=Sum('debit'))['total'] or 0
        balance = cr - dr
        return Response({'report': 'Accounts Payable Report', 'outstanding_payable': balance})

class CashFlowStatementView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        cash_accounts = Account.objects.filter(owner=owner, category=AccountCategory.ASSET).filter(name__icontains='Cash') | Account.objects.filter(owner=owner, category=AccountCategory.ASSET).filter(name__icontains='Bank')
        lines = JournalEntryLine.objects.filter(account__in=cash_accounts)
        
        cash_in = lines.aggregate(total=Sum('debit'))['total'] or 0
        cash_out = lines.aggregate(total=Sum('credit'))['total'] or 0
        
        return Response({
            'report': 'Cash Flow Statement',
            'total_cash_in': cash_in,
            'total_cash_out': cash_out,
            'net_cash_flow': cash_in - cash_out
        })

class SalesReportView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        revenues = JournalEntryLine.objects.filter(journal_entry__owner=owner, account__category=AccountCategory.REVENUE)
        sales_by_property = revenues.values('property__name').annotate(total_revenue=Sum('credit') - Sum('debit'))
        
        return Response({
            'report': 'Sales Report',
            'details': list(sales_by_property)
        })

class ExpenseReportView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        expenses = JournalEntryLine.objects.filter(journal_entry__owner=owner, account__category=AccountCategory.EXPENSE)
        expense_by_account = expenses.values('account__name').annotate(total_expense=Sum('debit') - Sum('credit'))
        
        return Response({
            'report': 'Expense Report',
            'details': list(expense_by_account)
        })

class InventoryReportView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        owner = request.user.get_data_owner()
        from properties.models import PropertyAsset
        assets = PropertyAsset.objects.filter(property__owner=owner)
        data = [{'property': a.property.name, 'name': a.name, 'quantity': a.quantity, 'condition': a.get_condition_display()} for a in assets]
        
        return Response({
            'report': 'Inventory Report',
            'assets': data
        })
