from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response

from .models import Tenant
from finance.models import Payment
from .serializers import TenantRegistrationSerializer, TenantSerializer


class TenantListCreateView(generics.ListCreateAPIView):
    def get_serializer_class(self):
        return TenantRegistrationSerializer if self.request.method == "POST" else TenantSerializer

    def get_queryset(self):
        return Tenant.objects.filter(owner=self.request.user).prefetch_related("rental_agreements__payments")


class TenantDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TenantSerializer

    def get_queryset(self):
        return Tenant.objects.filter(owner=self.request.user).prefetch_related("rental_agreements")

    def destroy(self, request, *args, **kwargs):
        tenant = self.get_object()
        if tenant.rental_agreements.exists():
            return Response({"detail": "Marka hore jooji ama tirtir heshiiska kirada."}, status=status.HTTP_400_BAD_REQUEST)
        tenant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EndTenantRentalView(generics.GenericAPIView):
    def get_queryset(self):
        return Tenant.objects.filter(owner=self.request.user)

    def post(self, request, pk):
        tenant = self.get_object()
        ended_count = tenant.rental_agreements.filter(status="active").update(
            status="ended", end_date=timezone.localdate()
        )
        if not ended_count:
            return Response({"detail": "Kiradu hore ayaa loo joojiyay."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Kirada waa la joojiyay."})


class TenantPaymentView(generics.GenericAPIView):
    def get_queryset(self):
        return Tenant.objects.filter(owner=self.request.user)

    def post(self, request, pk):
        tenant = self.get_object()
        agreement = tenant.rental_agreements.filter(status="active").first()
        if not agreement:
            return Response({"detail": "Kiraystahan ma laha heshiis socda."}, status=status.HTTP_400_BAD_REQUEST)
        amount = request.data.get("amount")
        if amount is None:
            return Response({"detail": "Geli lacagta la bixiyay."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            amount = float(amount)
            if amount <= 0 or amount > float(agreement.agreed_monthly_rent):
                raise ValueError
        except (TypeError, ValueError):
            return Response({"detail": "Lacagta la bixiyay ma saxna."}, status=status.HTTP_400_BAD_REQUEST)
        Payment.objects.create(rental_agreement=agreement, amount=amount, payment_date=timezone.localdate())
        return Response({"detail": "Lacag bixinta waa la kaydiyay."}, status=status.HTTP_201_CREATED)
