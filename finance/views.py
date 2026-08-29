from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response

from rentals.models import RentalAgreement
from .models import GeneralExpense, Payment


class PropertyExpenseView(generics.GenericAPIView):
    def get(self, request):
        expenses = GeneralExpense.objects.filter(property__owner=request.user).select_related("property").order_by("-expense_date")
        return Response([{"id": expense.id, "property_id": expense.property_id, "property_name": expense.property.name, "title": expense.title, "notes": expense.notes, "amount": expense.amount, "expense_date": expense.expense_date} for expense in expenses])

    def post(self, request):
        property_id = request.data.get("property_id")
        property_instance = request.user.properties.filter(id=property_id).first()
        if not property_instance:
            return Response({"detail": "Hantida lama helin."}, status=status.HTTP_400_BAD_REQUEST)
        title = request.data.get("title", "Dayactir")
        amount = request.data.get("amount")
        try:
            valid_amount = float(amount)
        except (TypeError, ValueError):
            valid_amount = 0
        if valid_amount <= 0:
            return Response({"detail": "Geli kharash sax ah."}, status=status.HTTP_400_BAD_REQUEST)
        expense = GeneralExpense.objects.create(property=property_instance, title=title, category="repair", amount=amount, expense_date=timezone.localdate(), notes=request.data.get("notes", ""))
        return Response({"id": expense.id, "property_id": expense.property_id, "amount": expense.amount}, status=status.HTTP_201_CREATED)


class PaymentListView(generics.ListAPIView):
    def get_queryset(self):
        return Payment.objects.filter(rental_agreement__tenant__owner=self.request.user).select_related("rental_agreement__tenant", "rental_agreement__property")

    def list(self, request, *args, **kwargs):
        month = int(request.query_params.get("month", timezone.localdate().month)); year = int(request.query_params.get("year", timezone.localdate().year))
        payments = self.get_queryset().filter(payment_date__month=month, payment_date__year=year).order_by("-payment_date", "-id")
        result = []
        for payment in payments:
            agreement = payment.rental_agreement
            paid = Payment.objects.filter(rental_agreement=agreement, payment_date__year=year, payment_date__month=month).aggregate(total=Sum("amount"))["total"] or 0
            result.append({"id": payment.id, "tenant_name": agreement.tenant.full_name, "property_name": agreement.property.name if agreement.property else "", "amount": payment.amount, "payment_date": payment.payment_date, "payment_time": payment.created_at.strftime("%H:%M"), "payment_method": payment.payment_method, "status": "paid" if paid >= agreement.agreed_monthly_rent else "partial"})
        return Response(result)


class PaymentSummaryView(generics.GenericAPIView):
    def get(self, request):
        today = timezone.localdate()
        month = int(request.query_params.get("month", today.month)); year = int(request.query_params.get("year", today.year))
        agreements = RentalAgreement.objects.filter(tenant__owner=request.user, status="active")
        payments = Payment.objects.filter(rental_agreement__in=agreements, payment_date__year=year, payment_date__month=month)
        expected = agreements.aggregate(total=Sum("agreed_monthly_rent"))["total"] or 0
        collected = payments.aggregate(total=Sum("amount"))["total"] or 0
        expenses = GeneralExpense.objects.filter(property__owner=request.user, expense_date__year=year, expense_date__month=month).aggregate(total=Sum("amount"))["total"] or 0
        paid_tenant_count = sum(1 for agreement in agreements if (payments.filter(rental_agreement=agreement).aggregate(total=Sum("amount"))["total"] or 0) >= agreement.agreed_monthly_rent)
        return Response({"expected": expected, "collected": collected, "unpaid": max(expected - collected, 0), "expenses": expenses, "net": collected - expenses, "paid_tenants": paid_tenant_count, "total_tenants": agreements.count()})


class MonthlyPaymentSummaryView(generics.GenericAPIView):
    def get(self, request):
        payments = Payment.objects.filter(rental_agreement__tenant__owner=request.user).annotate(month=TruncMonth("payment_date")).values("month").annotate(total=Sum("amount")).order_by("month")
        return Response([{"month": item["month"].strftime("%Y-%m"), "total": item["total"]} for item in payments])
