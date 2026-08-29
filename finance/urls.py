from django.urls import path
from .views import MonthlyPaymentSummaryView, PaymentListView, PaymentSummaryView, PropertyExpenseView

urlpatterns = [path("", PaymentListView.as_view()), path("summary/", PaymentSummaryView.as_view()), path("monthly-summary/", MonthlyPaymentSummaryView.as_view()), path("expenses/", PropertyExpenseView.as_view())]
