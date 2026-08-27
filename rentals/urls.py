from django.urls import path

from .views import EndTenantRentalView, TenantDetailView, TenantListCreateView, TenantPaymentView

urlpatterns = [path("", TenantListCreateView.as_view(), name="tenant-list"), path("<int:pk>/", TenantDetailView.as_view(), name="tenant-detail"), path("<int:pk>/end-rental/", EndTenantRentalView.as_view(), name="tenant-end-rental"), path("<int:pk>/pay/", TenantPaymentView.as_view(), name="tenant-payment")]
