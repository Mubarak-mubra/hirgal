from django.urls import path
from .views import (
    ChartOfAccountsView,
    IncomeStatementView,
    BalanceSheetView,
    TrialBalanceView,
    GeneralLedgerView,
    AccountsReceivableReportView,
    AccountsPayableReportView,
    CashFlowStatementView,
    SalesReportView,
    ExpenseReportView,
    InventoryReportView
)

urlpatterns = [
    path('reports/chart-of-accounts/', ChartOfAccountsView.as_view(), name='report-coa'),
    path('reports/income-statement/', IncomeStatementView.as_view(), name='report-income'),
    path('reports/balance-sheet/', BalanceSheetView.as_view(), name='report-balance-sheet'),
    path('reports/trial-balance/', TrialBalanceView.as_view(), name='report-trial-balance'),
    path('reports/general-ledger/', GeneralLedgerView.as_view(), name='report-general-ledger'),
    path('reports/accounts-receivable/', AccountsReceivableReportView.as_view(), name='report-ar'),
    path('reports/accounts-payable/', AccountsPayableReportView.as_view(), name='report-ap'),
    path('reports/cash-flow/', CashFlowStatementView.as_view(), name='report-cash-flow'),
    path('reports/sales/', SalesReportView.as_view(), name='report-sales'),
    path('reports/expense/', ExpenseReportView.as_view(), name='report-expense'),
    path('reports/inventory/', InventoryReportView.as_view(), name='report-inventory'),
]
