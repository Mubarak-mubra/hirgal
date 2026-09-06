from django.urls import path

from .views import (
    AccountCreateView, AccountDeleteView, AccountListView, AccountUpdateView,
    BankAccountCreateView, BankAccountDeleteView, BankAccountDetailView,
    BankAccountListView, BankAccountUpdateView,
    ChatbotView, ChatSessionDeleteView,
    DashboardView, GeneralExpenseCreateView, GeneralExpenseDeleteView,
    GeneralExpenseDetailView, GeneralExpenseListView, GeneralExpenseUpdateView,
    HomeView, InvoiceCreateView, InvoiceDeleteView, InvoiceDetailView,
    InvoiceListView, InvoiceUpdateView, JournalEntryCreateView,
    JournalEntryDeleteView, JournalEntryDetailView, JournalEntryListView,
    JournalEntryUpdateView, LoginView, LogoutView, MaintenanceRepairCreateView,
    MaintenanceRepairDeleteView, MaintenanceRepairDetailView,
    MaintenanceRepairListView, MaintenanceRepairUpdateView, PaymentCreateView,
    PaymentDeleteView, PaymentDetailView, PaymentListView, PaymentUpdateView,
    ProfileView, PropertyAssetCreateView, PropertyAssetDeleteView,
    PropertyAssetUpdateView, PropertyCreateView, PropertyDeleteView,
    PropertyDetailView, PropertyListView, PropertyUpdateView,
    RegisterView, RentalAgreementCreateView, RentalAgreementDeleteView,
    RentalAgreementListView, RentalAgreementUpdateView,
    RoomCreateView, RoomDeleteView, RoomUpdateView, TenantCreateView,
    TenantDeleteView, TenantDetailView, TenantListView, TenantUpdateView,
    UnitCreateView, UnitDeleteView, UnitUpdateView, UnitsByPropertyView,
    AgreementsByTenantView,
    VillaDetailsView,
)
from .accounting_views import (
    AccountingDashboardView,
    ChartOfAccountsView, IncomeStatementView, BalanceSheetView,
    TrialBalanceView, GeneralLedgerView, CashFlowStatementView,
    AccountsReceivableView, AccountsPayableView, SalesReportView,
    SalesReportDetailView, ExpenseReportView, ExpenseReportDetailView,
    InventoryReportView, ProfitLossView,
    AccountLedgerView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="web-login"),
    path("logout/", LogoutView.as_view(), name="web-logout"),
    path("register/", RegisterView.as_view(), name="web-register"),
    path("profile/", ProfileView.as_view(), name="web-profile"),
    path("api/units-by-property/", UnitsByPropertyView.as_view(), name="web-units-by-property"),
    path("api/agreements-by-tenant/", AgreementsByTenantView.as_view(), name="web-agreements-by-tenant"),
    path("", HomeView.as_view(), name="home"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),

    # Properties
    path("guryaha/", PropertyListView.as_view(), name="web-properties"),
    path("guryaha/new/", PropertyCreateView.as_view(), name="web-property-create"),
    path("guryaha/<int:pk>/", PropertyDetailView.as_view(), name="web-property-detail"),
    path("guryaha/<int:pk>/edit/", PropertyUpdateView.as_view(), name="web-property-edit"),
    path("guryaha/<int:pk>/delete/", PropertyDeleteView.as_view(), name="web-property-delete"),
    path("guryaha/<int:property_id>/alaab/new/", PropertyAssetCreateView.as_view(), name="web-asset-create"),
    path("guryaha/alaab/<int:pk>/edit/", PropertyAssetUpdateView.as_view(), name="web-asset-edit"),
    path("guryaha/alaab/<int:pk>/delete/", PropertyAssetDeleteView.as_view(), name="web-asset-delete"),
    path("guryaha/<int:property_id>/apartment/new/", UnitCreateView.as_view(), name="web-unit-create"),
    path("guryaha/<int:property_id>/villa/", VillaDetailsView.as_view(), name="web-villa-details"),
    path("guryaha/unit/<int:pk>/edit/", UnitUpdateView.as_view(), name="web-unit-edit"),
    path("guryaha/unit/<int:pk>/delete/", UnitDeleteView.as_view(), name="web-unit-delete"),
    path("guryaha/unit/<int:unit_id>/qol/new/", RoomCreateView.as_view(), name="web-room-create"),
    path("guryaha/qol/<int:pk>/edit/", RoomUpdateView.as_view(), name="web-room-edit"),
    path("guryaha/qol/<int:pk>/delete/", RoomDeleteView.as_view(), name="web-room-delete"),

    # Tenants
    path("kiraystayaal/", TenantListView.as_view(), name="web-tenants"),
    path("kiraystayaal/new/", TenantCreateView.as_view(), name="web-tenant-create"),
    path("kiraystayaal/<int:pk>/", TenantDetailView.as_view(), name="web-tenant-detail"),
    path("kiraystayaal/<int:pk>/edit/", TenantUpdateView.as_view(), name="web-tenant-edit"),
    path("kiraystayaal/<int:pk>/delete/", TenantDeleteView.as_view(), name="web-tenant-delete"),

    # Rental Agreements
    path("heshiisyada/", RentalAgreementListView.as_view(), name="web-agreements"),
    path("heshiisyada/new/", RentalAgreementCreateView.as_view(), name="web-agreement-create"),
    path("heshiisyada/<int:pk>/edit/", RentalAgreementUpdateView.as_view(), name="web-agreement-edit"),
    path("heshiisyada/<int:pk>/delete/", RentalAgreementDeleteView.as_view(), name="web-agreement-delete"),

    # Payments
    path("lacag-bixinta/", PaymentListView.as_view(), name="web-payments"),
    path("lacag-bixinta/new/", PaymentCreateView.as_view(), name="web-payment-create"),
    path("lacag-bixinta/<int:pk>/", PaymentDetailView.as_view(), name="web-payment-detail"),
    path("lacag-bixinta/<int:pk>/edit/", PaymentUpdateView.as_view(), name="web-payment-edit"),
    path("lacag-bixinta/<int:pk>/delete/", PaymentDeleteView.as_view(), name="web-payment-delete"),

    # Bank Accounts
    path("xisaabaha-bangiga/", BankAccountListView.as_view(), name="web-bank-accounts"),
    path("xisaabaha-bangiga/new/", BankAccountCreateView.as_view(), name="web-bank-account-create"),
    path("xisaabaha-bangiga/<int:pk>/", BankAccountDetailView.as_view(), name="web-bank-account-detail"),
    path("xisaabaha-bangiga/<int:pk>/edit/", BankAccountUpdateView.as_view(), name="web-bank-account-edit"),
    path("xisaabaha-bangiga/<int:pk>/delete/", BankAccountDeleteView.as_view(), name="web-bank-account-delete"),

    # Maintenance / Repairs
    path("dayactirka/", MaintenanceRepairListView.as_view(), name="web-maintenance-list"),
    path("dayactirka/new/", MaintenanceRepairCreateView.as_view(), name="web-maintenance-create"),
    path("dayactirka/<int:pk>/", MaintenanceRepairDetailView.as_view(), name="web-maintenance-detail"),
    path("dayactirka/<int:pk>/edit/", MaintenanceRepairUpdateView.as_view(), name="web-maintenance-edit"),
    path("dayactirka/<int:pk>/delete/", MaintenanceRepairDeleteView.as_view(), name="web-maintenance-delete"),

    # General Expenses
    path("kharashka/", GeneralExpenseListView.as_view(), name="web-expense-list"),
    path("kharashka/new/", GeneralExpenseCreateView.as_view(), name="web-expense-create"),
    path("kharashka/<int:pk>/", GeneralExpenseDetailView.as_view(), name="web-expense-detail"),
    path("kharashka/<int:pk>/edit/", GeneralExpenseUpdateView.as_view(), name="web-expense-edit"),
    path("kharashka/<int:pk>/delete/", GeneralExpenseDeleteView.as_view(), name="web-expense-delete"),

    # Accounting - Accounts
    path("xisaabiyadda/xisaabo/", AccountListView.as_view(), name="web-account-list"),
    path("xisaabiyadda/xisaabo/new/", AccountCreateView.as_view(), name="web-account-create"),
    path("xisaabiyadda/xisaabo/<int:pk>/", AccountLedgerView.as_view(), name="web-account-ledger"),
    path("xisaabiyadda/xisaabo/<int:pk>/edit/", AccountUpdateView.as_view(), name="web-account-edit"),
    path("xisaabiyadda/xisaabo/<int:pk>/delete/", AccountDeleteView.as_view(), name="web-account-delete"),

    # Accounting - Journal Entries
    path("xisaabiyadda/diiwaanka/", JournalEntryListView.as_view(), name="web-journal-list"),
    path("xisaabiyadda/diiwaanka/new/", JournalEntryCreateView.as_view(), name="web-journal-create"),
    path("xisaabiyadda/diiwaanka/<int:pk>/", JournalEntryDetailView.as_view(), name="web-journal-detail"),
    path("xisaabiyadda/diiwaanka/<int:pk>/edit/", JournalEntryUpdateView.as_view(), name="web-journal-edit"),
    path("xisaabiyadda/diiwaanka/<int:pk>/delete/", JournalEntryDeleteView.as_view(), name="web-journal-delete"),

    # Accounting - Invoices
    path("xisaabiyadda/biilasha/", InvoiceListView.as_view(), name="web-invoice-list"),
    path("xisaabiyadda/biilasha/new/", InvoiceCreateView.as_view(), name="web-invoice-create"),
    path("xisaabiyadda/biilasha/<int:pk>/", InvoiceDetailView.as_view(), name="web-invoice-detail"),
    path("xisaabiyadda/biilasha/<int:pk>/edit/", InvoiceUpdateView.as_view(), name="web-invoice-edit"),
    path("xisaabiyadda/biilasha/<int:pk>/delete/", InvoiceDeleteView.as_view(), name="web-invoice-delete"),

    # Accounting - Reports
    path("xisaabiyadda/", AccountingDashboardView.as_view(), name="web-accounting-dashboard"),
    path("xisaabiyadda/xisaabaha/", ChartOfAccountsView.as_view(), name="web-chart-of-accounts"),
    path("xisaabiyadda/dakhli-kharash/", IncomeStatementView.as_view(), name="web-income-statement"),
    path("xisaabiyadda/misuq/", BalanceSheetView.as_view(), name="web-balance-sheet"),
    path("xisaabiyadda/isku-dhafka/", TrialBalanceView.as_view(), name="web-trial-balance"),
    path("xisaabiyadda/gelidda-guud/", GeneralLedgerView.as_view(), name="web-general-ledger"),
    path("xisaabiyadda/daqliga-lacagta/", CashFlowStatementView.as_view(), name="web-cash-flow"),
    path("xisaabiyadda/lacagaha-la-waito/", AccountsReceivableView.as_view(), name="web-ar"),
    path("xisaabiyadda/lacagaha-la-bixiyo/", AccountsPayableView.as_view(), name="web-ap"),
    path("xisaabiyadda/iibka/", SalesReportView.as_view(), name="web-sales-report"),
    path("xisaabiyadda/iibka/<int:property_id>/", SalesReportDetailView.as_view(), name="web-sales-report-detail"),
    path("xisaabiyadda/kharashka-warbixinta/", ExpenseReportView.as_view(), name="web-expense-report"),
    path("xisaabiyadda/kharashka-warbixinta/<int:account_id>/", ExpenseReportDetailView.as_view(), name="web-expense-report-detail"),
    path("xisaabiyadda/alaabaha/", InventoryReportView.as_view(), name="web-inventory-report"),
    path("xisaabiyadda/faa'iida-khasnaha/", ProfitLossView.as_view(), name="web-profit-loss"),
    path("ai/", ChatbotView.as_view(), name="web-chatbot"),
    path("ai/<int:pk>/delete/", ChatSessionDeleteView.as_view(), name="web-chat-session-delete"),
]
