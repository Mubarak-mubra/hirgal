from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, TemplateView, ListView

from django.db import transaction
from accounting.models import Account, Invoice, InvoiceLine, JournalEntry, JournalEntryLine
from accounting.services import (
    link_bank_account_to_ledger, post_expense, post_payment, post_repair,
    seed_default_chart_of_accounts,
)
from finance.models import BankAccount, GeneralExpense, MaintenanceRepair, Payment
from properties.models import Property, PropertyAsset, Room, Unit
from rentals.models import RentalAgreement, Tenant

from .forms import (
    AccountForm, BankAccountForm, GeneralExpenseForm, InvoiceForm, InvoiceLineFormSet,
    JournalEntryForm, JournalEntryLineFormSet, MaintenanceRepairForm,
    PaymentForm, PropertyAssetForm, PropertyForm, RegistrationForm,
    RentalAgreementForm, RoomForm, TenantForm, UnitForm, UserProfileForm,
    VillaDetailsForm,
)


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "web/home.html"
    login_url = "/login/"


class DashboardView(TemplateView):
    template_name = "web/dashboard.html"
    login_url = "/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user.get_data_owner()
        from datetime import date
        today = date.today()
        first_day_of_month = today.replace(day=1)

        # Counts
        context["property_count"] = Property.objects.filter(owner=user).count()
        context["tenant_count"] = Tenant.objects.filter(owner=user).count()
        context["agreement_count"] = RentalAgreement.objects.filter(tenant__owner=user, status="active").count()
        context["invoice_count"] = Invoice.objects.filter(owner=user, status="sent").count()

        # Financials
        all_payments = Payment.objects.filter(rental_agreement__tenant__owner=user)
        all_expenses = GeneralExpense.objects.filter(property__owner=user)
        all_repairs = MaintenanceRepair.objects.filter(property__owner=user)

        context["payment_count"] = all_payments.count()
        context["total_revenue"] = sum(p.amount for p in all_payments)
        context["expense_total"] = sum(e.amount for e in all_expenses)
        context["repair_total"] = sum(r.repair_cost for r in all_repairs)
        context["net_income"] = context["total_revenue"] - context["expense_total"] - context["repair_total"]

        # Bank accounts
        from finance.models import BankAccount
        bank_accounts = BankAccount.objects.filter(owner=user, is_active=True)
        context["bank_balance"] = sum(
            sum(p.amount for p in bank.payments.all()) - sum(e.amount for e in bank.general_expenses.all()) - sum(r.repair_cost for r in bank.maintenance_repairs.all())
            for bank in bank_accounts
        )

        # Recent activity
        context["recent_payments"] = all_payments.select_related(
            "rental_agreement__tenant", "rental_agreement__property"
        ).order_by("-payment_date")[:5]
        context["recent_expenses"] = all_expenses.select_related("property").order_by("-expense_date")[:5]
        context["recent_repairs"] = all_repairs.select_related("property").order_by("-reported_date")[:5]

        # Occupancy
        total_units = sum(p.total_rentable_spaces for p in Property.objects.filter(owner=user))
        rented_units = RentalAgreement.objects.filter(tenant__owner=user, status="active").count()
        context["occupancy_rate"] = round((rented_units / total_units * 100) if total_units > 0 else 0, 1)
        context["total_units"] = total_units
        context["rented_units"] = rented_units

        # Outstanding AR
        from accounting.models import Account, JournalEntryLine
        from django.db.models import Sum
        ar_account = Account.objects.filter(owner=user, code="1200").first()
        if ar_account:
            ar_lines = ar_account.journal_lines.all()
            dr = ar_lines.aggregate(total=Sum("debit"))["total"] or 0
            cr = ar_lines.aggregate(total=Sum("credit"))["total"] or 0
            context["ar_balance"] = dr - cr
        else:
            context["ar_balance"] = 0

        # ── Rent Status This Month ──────────────────────────────────────────
        active_agreements = RentalAgreement.objects.filter(
            tenant__owner=user, status="active"
        ).select_related("tenant", "property", "unit")

        paid_full = []      # Paid full rent this month
        paid_partial = []   # Paid but not full amount
        not_paid = []       # No payment this month

        for agreement in active_agreements:
            # Get all payments for this agreement this month
            month_payments = Payment.objects.filter(
                rental_agreement=agreement,
                payment_date__gte=first_day_of_month,
                payment_date__lte=today,
            )
            total_paid = sum(p.amount for p in month_payments)
            monthly_rent = agreement.monthly_rent

            item = {
                "agreement": agreement,
                "monthly_rent": monthly_rent,
                "total_paid": total_paid,
                "remaining": monthly_rent - total_paid,
            }

            if total_paid >= monthly_rent:
                paid_full.append(item)
            elif total_paid > 0:
                paid_partial.append(item)
            else:
                not_paid.append(item)

        context["rent_paid_full"] = paid_full
        context["rent_paid_partial"] = paid_partial
        context["rent_not_paid"] = not_paid
        context["rent_total_expected"] = sum(a.monthly_rent for a in active_agreements)
        context["rent_total_collected"] = sum(
            sum(p.amount for p in Payment.objects.filter(
                rental_agreement=a,
                payment_date__gte=first_day_of_month,
                payment_date__lte=today,
            ))
            for a in active_agreements
        )

        return context


class UnitsByPropertyView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        property_id = request.GET.get("property_id")
        if not property_id:
            return JsonResponse({"units": []})

        # Get all units for this property
        all_units = Unit.objects.filter(property_id=property_id)

        # Get unit IDs that have active agreements
        rented_unit_ids = RentalAgreement.objects.filter(
            property_id=property_id,
            status="active",
            unit__isnull=False
        ).values_list("unit_id", flat=True)

        # Filter out rented units
        available_units = all_units.exclude(id__in=rented_unit_ids).values("id", "unit_number")

        return JsonResponse({"units": list(available_units)})


class AgreementsByTenantView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        tenant_id = request.GET.get("tenant_id")
        if not tenant_id:
            return JsonResponse({"agreements": []})
        agreements = RentalAgreement.objects.filter(
            tenant_id=tenant_id,
            status="active",
        ).select_related("unit", "property").values(
            "id", "unit__unit_number", "property__name", "monthly_rent"
        )
        result = []
        for a in agreements:
            label = f"{a['property__name']}"
            if a["unit__unit_number"]:
                label += f" - {a['unit__unit_number']}"
            label += f" (${a['monthly_rent']}/mo)"
            result.append({"id": a["id"], "label": label})
        return JsonResponse({"agreements": result})


class CheckTenantPaidView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        from django.utils import timezone
        tenant_id = request.GET.get("tenant_id")
        if not tenant_id:
            return JsonResponse({"paid": False})

        now = timezone.now()
        existing = Payment.objects.filter(
            rental_agreement__tenant_id=tenant_id,
            payment_date__year=now.year,
            payment_date__month=now.month,
        ).select_related("rental_agreement__tenant")

        if existing.exists():
            total = sum(p.amount for p in existing)
            tenant_name = existing.first().rental_agreement.tenant.full_name
            return JsonResponse({
                "paid": True,
                "tenant_name": tenant_name,
                "total_paid": float(total),
                "count": existing.count(),
            })
        return JsonResponse({"paid": False})


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("home")
        return render(request, "web/register.html", {"form": RegistrationForm()})

    def post(self, request):
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password"])
            user.save()
            seed_default_chart_of_accounts(user)
            login(request, user)
            return redirect("home")
        return render(request, "web/register.html", {"form": form})


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("home")
        return render(request, "web/login.html")

    def post(self, request):
        identifier = request.POST.get("username_or_phone", "").strip()
        password = request.POST.get("password", "")
        user_model = get_user_model()
        user = user_model.objects.filter(username=identifier).first()
        if user is None:
            user = user_model.objects.filter(phone_number=identifier).first()
        if user and user.check_password(password) and user.is_active and user.is_approved:
            if not Account.objects.filter(owner=user).exists():
                seed_default_chart_of_accounts(user)
            login(request, user)
            return redirect(request.GET.get("next", "home"))
        return render(request, "web/login.html", {"error_message": "Xogta gelitaanka waa khalad ama akoonka wali lama ansixin."})


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("web-login")


class ProfileView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        form = UserProfileForm(instance=request.user)
        return render(request, "web/profile.html", {"form": form})

    def post(self, request):
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect("web-profile")
        return render(request, "web/profile.html", {"form": form})


# ── Properties ────────────────────────────────────────────────────────────────

class PropertyListView(HomeView):
    template_name = "web/property_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        properties = Property.objects.filter(owner=self.request.user.get_data_owner()).prefetch_related("assets")
        # Prefetch active agreements for each property
        for prop in properties:
            prop.active_agreements = prop.rental_agreements.filter(status="active").select_related("tenant", "unit")
        context["properties"] = properties
        return context

    def post(self, request):
        form = PropertyForm(request.POST)
        if form.is_valid():
            property_instance = form.save(commit=False)
            property_instance.owner = request.user.get_data_owner()
            property_instance.total_rentable_spaces = 0
            property_instance.save()
        return redirect("web-properties")


class PropertyCreateView(HomeView):
    template_name = "web/property_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = PropertyForm()
        return context

    def post(self, request):
        form = PropertyForm(request.POST)
        if form.is_valid():
            property_instance = form.save(commit=False)
            property_instance.owner = request.user.get_data_owner()
            property_instance.save()
            return redirect("web-property-detail", property_instance.pk)
        return render(request, self.template_name, {"form": form})


class PropertyDetailView(LoginRequiredMixin, DetailView):
    model = Property
    template_name = "web/property_detail.html"
    context_object_name = "property"
    login_url = "/login/"

    def get_queryset(self):
        return Property.objects.filter(owner=self.request.user.get_data_owner()).prefetch_related(
            "assets", "units__rooms", "rental_agreements__tenant", "general_expenses"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agreements = self.object.rental_agreements.filter(status="active")
        context["active_agreements"] = agreements
        context["expected_rent"] = sum(item.agreed_monthly_rent for item in agreements)
        context["monthly_expenses"] = sum(item.amount for item in self.object.general_expenses.all())
        context["space_count"] = sum(unit.rooms.count() for unit in self.object.units.all()) if self.object.property_type == "home" else self.object.units.count()
        return context


class PropertyUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        property_instance = get_object_or_404(Property, pk=pk, owner=request.user.get_data_owner())
        form = PropertyForm(instance=property_instance)
        return render(request, "web/property_form.html", {"form": form, "editing": True})

    def post(self, request, pk):
        property_instance = get_object_or_404(Property, pk=pk, owner=request.user.get_data_owner())
        form = PropertyForm(request.POST, instance=property_instance)
        if form.is_valid():
            form.save()
            return redirect("web-property-detail", pk)
        return render(request, "web/property_form.html", {"form": form, "editing": True})


class PropertyDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        property_instance = get_object_or_404(Property, pk=pk, owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": property_instance, "cancel_url": "web-property-detail", "cancel_args": [pk]})

    def post(self, request, pk):
        property_instance = get_object_or_404(Property, pk=pk, owner=request.user.get_data_owner())
        property_instance.delete()
        return redirect("web-properties")


# ── Assets ────────────────────────────────────────────────────────────────────

class PropertyAssetCreateView(HomeView):
    template_name = "web/asset_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["property"] = get_object_or_404(Property, pk=self.kwargs["property_id"], owner=self.request.user.get_data_owner())
        context["form"] = PropertyAssetForm()
        return context

    def post(self, request, property_id):
        property_instance = get_object_or_404(Property, pk=property_id, owner=request.user.get_data_owner())
        form = PropertyAssetForm(request.POST)
        if form.is_valid():
            asset = form.save(commit=False)
            asset.property = property_instance
            asset.save()
            return redirect("web-property-detail", property_instance.pk)
        return render(request, self.template_name, {"property": property_instance, "form": form})


class PropertyAssetUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        asset = get_object_or_404(PropertyAsset, pk=pk, property__owner=request.user.get_data_owner())
        form = PropertyAssetForm(instance=asset)
        return render(request, "web/asset_form.html", {"property": asset.property, "form": form, "editing": True})

    def post(self, request, pk):
        asset = get_object_or_404(PropertyAsset, pk=pk, property__owner=request.user.get_data_owner())
        form = PropertyAssetForm(request.POST, instance=asset)
        if form.is_valid():
            form.save()
            return redirect("web-property-detail", asset.property_id)
        return render(request, "web/asset_form.html", {"property": asset.property, "form": form, "editing": True})


class PropertyAssetDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        asset = get_object_or_404(PropertyAsset, pk=pk, property__owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": asset, "cancel_url": "web-property-detail", "cancel_args": [asset.property_id]})

    def post(self, request, pk):
        asset = get_object_or_404(PropertyAsset, pk=pk, property__owner=request.user.get_data_owner())
        prop_id = asset.property_id
        asset.delete()
        return redirect("web-property-detail", prop_id)


# ── Units ─────────────────────────────────────────────────────────────────────

class UnitCreateView(HomeView):
    template_name = "web/unit_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["property"] = get_object_or_404(Property, pk=self.kwargs["property_id"], owner=self.request.user.get_data_owner())
        context["form"] = UnitForm()
        return context

    def post(self, request, property_id):
        property_instance = get_object_or_404(Property, pk=property_id, owner=request.user.get_data_owner())
        form = UnitForm(request.POST)
        if form.is_valid():
            unit = form.save(commit=False)
            unit.property = property_instance
            unit.save()
            return redirect("web-property-detail", property_instance.pk)
        return render(request, self.template_name, {"property": property_instance, "form": form})


class UnitUpdateView(HomeView):
    template_name = "web/unit_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        unit = get_object_or_404(Unit, pk=self.kwargs["pk"], property__owner=self.request.user.get_data_owner())
        context.update({"property": unit.property, "form": UnitForm(instance=unit), "editing": True})
        return context

    def post(self, request, pk):
        unit = get_object_or_404(Unit, pk=pk, property__owner=request.user.get_data_owner())
        form = UnitForm(request.POST, instance=unit)
        if form.is_valid():
            form.save()
            return redirect("web-property-detail", unit.property_id)
        return render(request, self.template_name, {"property": unit.property, "form": form, "editing": True})


class UnitDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        unit = get_object_or_404(Unit, pk=pk, property__owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": unit, "cancel_url": "web-property-detail", "cancel_args": [unit.property_id]})

    def post(self, request, pk):
        unit = get_object_or_404(Unit, pk=pk, property__owner=request.user.get_data_owner())
        prop_id = unit.property_id
        unit.delete()
        return redirect("web-property-detail", prop_id)


# ── Rooms ─────────────────────────────────────────────────────────────────────

class VillaDetailsView(HomeView):
    template_name = "web/villa_form.html"

    def get_property(self):
        return get_object_or_404(Property, pk=self.kwargs["property_id"], owner=self.request.user.get_data_owner())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        property_instance = self.get_property()
        existing_unit = property_instance.units.first()
        initial = {"total_rooms": existing_unit.total_rooms, "bathrooms": existing_unit.bathrooms, "living_rooms": existing_unit.living_rooms} if existing_unit else None
        context.update({"property": property_instance, "form": VillaDetailsForm(initial=initial), "editing": bool(existing_unit)})
        return context

    def post(self, request, property_id):
        property_instance = self.get_property()
        form = VillaDetailsForm(request.POST)
        if form.is_valid():
            unit, created = Unit.objects.get_or_create(property=property_instance, unit_number="Filo")
            unit.unit_type = "house"
            unit.rental_mode = "whole_unit"
            unit.total_rooms = form.cleaned_data["total_rooms"]
            unit.bathrooms = form.cleaned_data["bathrooms"]
            unit.living_rooms = form.cleaned_data["living_rooms"]
            unit.save()
            return redirect("web-property-detail", property_instance.pk)
        return render(request, self.template_name, {"property": property_instance, "form": form})


class RoomCreateView(HomeView):
    template_name = "web/room_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unit"] = get_object_or_404(Unit, pk=self.kwargs["unit_id"], property__owner=self.request.user.get_data_owner())
        context["form"] = RoomForm()
        return context

    def post(self, request, unit_id):
        unit = get_object_or_404(Unit, pk=unit_id, property__owner=request.user.get_data_owner())
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            room.unit = unit
            room.monthly_rent = 0
            room.save()
            return redirect("web-property-detail", unit.property_id)
        return render(request, self.template_name, {"unit": unit, "form": form})


class RoomUpdateView(HomeView):
    template_name = "web/room_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        room = get_object_or_404(Room, pk=self.kwargs["pk"], unit__property__owner=self.request.user.get_data_owner())
        context.update({"unit": room.unit, "form": RoomForm(instance=room), "editing": True})
        return context

    def post(self, request, pk):
        room = get_object_or_404(Room, pk=pk, unit__property__owner=request.user.get_data_owner())
        form = RoomForm(request.POST, instance=room)
        if form.is_valid():
            form.save()
            return redirect("web-property-detail", room.unit.property_id)
        return render(request, self.template_name, {"unit": room.unit, "form": form, "editing": True})


class RoomDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        room = get_object_or_404(Room, pk=pk, unit__property__owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": room, "cancel_url": "web-property-detail", "cancel_args": [room.unit.property_id]})

    def post(self, request, pk):
        room = get_object_or_404(Room, pk=pk, unit__property__owner=request.user.get_data_owner())
        prop_id = room.unit.property_id
        room.delete()
        return redirect("web-property-detail", prop_id)


# ── Tenants ───────────────────────────────────────────────────────────────────

class TenantListView(HomeView):
    template_name = "web/tenant_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tenants"] = Tenant.objects.filter(owner=self.request.user.get_data_owner()).prefetch_related("rental_agreements")
        return context


class TenantDetailView(HomeView):
    template_name = "web/tenant_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tenant"] = get_object_or_404(Tenant, pk=self.kwargs["pk"], owner=self.request.user.get_data_owner())
        return context


class TenantCreateView(HomeView):
    template_name = "web/tenant_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["properties"] = Property.objects.filter(owner=self.request.user.get_data_owner())
        return context

    def post(self, request):
        tenant, created = Tenant.objects.get_or_create(
            owner=request.user.get_data_owner(), phone_number=request.POST.get("phone_number"),
            defaults={"full_name": request.POST.get("full_name"), "tenant_type": request.POST.get("tenant_type", "person")},
        )
        property_instance = get_object_or_404(Property, pk=request.POST.get("property_id"), owner=request.user.get_data_owner())
        RentalAgreement.objects.create(
            tenant=tenant, property=property_instance, rental_scope="whole_property",
            rented_space_count=property_instance.total_rentable_spaces,
            agreed_monthly_rent=request.POST.get("agreed_monthly_rent"),
            monthly_rent=request.POST.get("agreed_monthly_rent"),
            start_date=request.POST.get("start_date"),
        )
        return redirect("web-tenant-detail", tenant.pk)


class TenantUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk, owner=request.user.get_data_owner())
        form = TenantForm(instance=tenant)
        return render(request, "web/tenant_form.html", {"form": form, "editing": True, "tenant": tenant})

    def post(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk, owner=request.user.get_data_owner())
        form = TenantForm(request.POST, instance=tenant)
        if form.is_valid():
            form.save()
            return redirect("web-tenant-detail", pk)
        return render(request, "web/tenant_form.html", {"form": form, "editing": True, "tenant": tenant})


class TenantDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk, owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": tenant, "cancel_url": "web-tenants"})

    def post(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk, owner=request.user.get_data_owner())
        tenant.delete()
        return redirect("web-tenants")


# ── Rental Agreements ────────────────────────────────────────────────────────

class RentalAgreementListView(HomeView):
    template_name = "web/agreement_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["agreements"] = RentalAgreement.objects.filter(
            tenant__owner=self.request.user.get_data_owner()
        ).select_related("tenant", "property", "unit", "room").order_by("-start_date")
        return context


class RentalAgreementCreateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        tenant_id = request.GET.get("tenant")
        form = RentalAgreementForm(user=request.user.get_data_owner(), tenant_id=tenant_id)
        return render(request, "web/agreement_form.html", {"form": form, "tenant_id": tenant_id})

    def post(self, request):
        tenant_id = request.GET.get("tenant") or request.POST.get("tenant")
        form = RentalAgreementForm(request.POST, user=request.user.get_data_owner(), tenant_id=tenant_id)
        if form.is_valid():
            form.save()
            return redirect("web-tenant-detail", tenant_id) if tenant_id else redirect("web-agreements")
        return render(request, "web/agreement_form.html", {"form": form, "tenant_id": tenant_id})


class RentalAgreementUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        agreement = get_object_or_404(RentalAgreement, pk=pk, tenant__owner=request.user.get_data_owner())
        form = RentalAgreementForm(instance=agreement, user=request.user.get_data_owner())
        return render(request, "web/agreement_form.html", {"form": form, "editing": True})

    def post(self, request, pk):
        agreement = get_object_or_404(RentalAgreement, pk=pk, tenant__owner=request.user.get_data_owner())
        form = RentalAgreementForm(request.POST, instance=agreement, user=request.user.get_data_owner())
        if form.is_valid():
            form.save()
            return redirect("web-agreements")
        return render(request, "web/agreement_form.html", {"form": form, "editing": True})


class RentalAgreementDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        agreement = get_object_or_404(RentalAgreement, pk=pk, tenant__owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": agreement, "cancel_url": "web-agreements"})

    def post(self, request, pk):
        agreement = get_object_or_404(RentalAgreement, pk=pk, tenant__owner=request.user.get_data_owner())
        agreement.delete()
        return redirect("web-agreements")


# ── Payments ──────────────────────────────────────────────────────────────────

class PaymentListView(HomeView):
    template_name = "web/payment_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["payments"] = Payment.objects.filter(
            rental_agreement__tenant__owner=self.request.user.get_data_owner()
        ).select_related("rental_agreement__tenant", "rental_agreement__property").order_by("-payment_date", "-id")[:100]
        return context


class PaymentDetailView(LoginRequiredMixin, DetailView):
    model = Payment
    template_name = "web/payment_detail.html"
    context_object_name = "payment"
    login_url = "/login/"

    def get_queryset(self):
        return Payment.objects.filter(rental_agreement__tenant__owner=self.request.user.get_data_owner()).select_related(
            "rental_agreement__tenant", "rental_agreement__property", "destination_account"
        )


class PaymentCreateView(HomeView):
    template_name = "web/payment_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = PaymentForm(user=self.request.user.get_data_owner())
        return context

    def post(self, request):
        form = PaymentForm(request.POST, user=request.user.get_data_owner())
        if form.is_valid():
            with transaction.atomic():
                form.save()
            return redirect("web-payments")
        return render(request, self.template_name, {"form": form})


class PaymentUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk, rental_agreement__tenant__owner=request.user.get_data_owner())
        form = PaymentForm(instance=payment, user=request.user.get_data_owner())
        return render(request, "web/payment_form.html", {"form": form, "editing": True})

    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk, rental_agreement__tenant__owner=request.user.get_data_owner())
        form = PaymentForm(request.POST, instance=payment, user=request.user.get_data_owner())
        if form.is_valid():
            with transaction.atomic():
                form.save()
            return redirect("web-payments")
        return render(request, "web/payment_form.html", {"form": form, "editing": True})


class PaymentDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk, rental_agreement__tenant__owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": payment, "cancel_url": "web-payments"})

    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk, rental_agreement__tenant__owner=request.user.get_data_owner())
        payment.delete()
        return redirect("web-payments")


# ── Maintenance / Repairs ────────────────────────────────────────────────────

class MaintenanceRepairListView(HomeView):
    template_name = "web/maintenance_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["repairs"] = MaintenanceRepair.objects.filter(
            property__owner=self.request.user.get_data_owner()
        ).select_related("property", "unit", "reported_by_tenant").order_by("-reported_date")
        return context


class MaintenanceRepairDetailView(LoginRequiredMixin, DetailView):
    model = MaintenanceRepair
    template_name = "web/maintenance_detail.html"
    context_object_name = "repair"
    login_url = "/login/"

    def get_queryset(self):
        return MaintenanceRepair.objects.filter(property__owner=self.request.user.get_data_owner()).select_related("property", "unit", "reported_by_tenant", "expense_account")


class MaintenanceRepairCreateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        form = MaintenanceRepairForm(user=request.user.get_data_owner())
        return render(request, "web/maintenance_form.html", {"form": form})

    def post(self, request):
        form = MaintenanceRepairForm(request.POST, user=request.user.get_data_owner())
        if form.is_valid():
            with transaction.atomic():
                form.save()
            return redirect("web-maintenance-list")
        return render(request, "web/maintenance_form.html", {"form": form})


class MaintenanceRepairUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        repair = get_object_or_404(MaintenanceRepair, pk=pk, property__owner=request.user.get_data_owner())
        form = MaintenanceRepairForm(instance=repair, user=request.user.get_data_owner())
        return render(request, "web/maintenance_form.html", {"form": form, "editing": True})

    def post(self, request, pk):
        repair = get_object_or_404(MaintenanceRepair, pk=pk, property__owner=request.user.get_data_owner())
        form = MaintenanceRepairForm(request.POST, instance=repair, user=request.user.get_data_owner())
        if form.is_valid():
            with transaction.atomic():
                form.save()
            return redirect("web-maintenance-detail", pk)
        return render(request, "web/maintenance_form.html", {"form": form, "editing": True})


class MaintenanceRepairDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        repair = get_object_or_404(MaintenanceRepair, pk=pk, property__owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": repair, "cancel_url": "web-maintenance-list"})

    def post(self, request, pk):
        repair = get_object_or_404(MaintenanceRepair, pk=pk, property__owner=request.user.get_data_owner())
        repair.delete()
        return redirect("web-maintenance-list")


# ── General Expenses ──────────────────────────────────────────────────────────

class GeneralExpenseListView(HomeView):
    template_name = "web/expense_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["expenses"] = GeneralExpense.objects.filter(
            property__owner=self.request.user.get_data_owner()
        ).select_related("property", "expense_account").order_by("-expense_date")
        return context


class GeneralExpenseDetailView(LoginRequiredMixin, DetailView):
    model = GeneralExpense
    template_name = "web/expense_detail.html"
    context_object_name = "expense"
    login_url = "/login/"

    def get_queryset(self):
        return GeneralExpense.objects.filter(property__owner=self.request.user.get_data_owner()).select_related("property", "expense_account")


class GeneralExpenseCreateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        form = GeneralExpenseForm(user=request.user.get_data_owner())
        return render(request, "web/expense_form.html", {"form": form})

    def post(self, request):
        form = GeneralExpenseForm(request.POST, user=request.user.get_data_owner())
        if form.is_valid():
            with transaction.atomic():
                form.save()
            return redirect("web-expense-list")
        return render(request, "web/expense_form.html", {"form": form})


class GeneralExpenseUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        expense = get_object_or_404(GeneralExpense, pk=pk, property__owner=request.user.get_data_owner())
        form = GeneralExpenseForm(instance=expense, user=request.user.get_data_owner())
        return render(request, "web/expense_form.html", {"form": form, "editing": True})

    def post(self, request, pk):
        expense = get_object_or_404(GeneralExpense, pk=pk, property__owner=request.user.get_data_owner())
        form = GeneralExpenseForm(request.POST, instance=expense, user=request.user.get_data_owner())
        if form.is_valid():
            with transaction.atomic():
                form.save()
            return redirect("web-expense-detail", pk)
        return render(request, "web/expense_form.html", {"form": form, "editing": True})


class GeneralExpenseDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        expense = get_object_or_404(GeneralExpense, pk=pk, property__owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": expense, "cancel_url": "web-expense-list"})

    def post(self, request, pk):
        expense = get_object_or_404(GeneralExpense, pk=pk, property__owner=request.user.get_data_owner())
        expense.delete()
        return redirect("web-expense-list")


# ── Accounts ──────────────────────────────────────────────────────────────────

class AccountListView(HomeView):
    template_name = "web/account_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["accounts"] = Account.objects.filter(owner=self.request.user.get_data_owner())
        return context


class AccountCreateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        form = AccountForm(user=request.user.get_data_owner())
        return render(request, "web/account_form.html", {"form": form})

    def post(self, request):
        form = AccountForm(request.POST, user=request.user.get_data_owner())
        if form.is_valid():
            account = form.save(commit=False)
            account.owner = request.user.get_data_owner()
            account.save()
            return redirect("web-account-list")
        return render(request, "web/account_form.html", {"form": form})


class AccountUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        account = get_object_or_404(Account, pk=pk, owner=request.user.get_data_owner())
        form = AccountForm(instance=account, user=request.user.get_data_owner())
        return render(request, "web/account_form.html", {"form": form, "editing": True})

    def post(self, request, pk):
        account = get_object_or_404(Account, pk=pk, owner=request.user.get_data_owner())
        form = AccountForm(request.POST, instance=account, user=request.user.get_data_owner())
        if form.is_valid():
            form.save()
            return redirect("web-account-list")
        return render(request, "web/account_form.html", {"form": form, "editing": True})


class AccountDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        account = get_object_or_404(Account, pk=pk, owner=request.user.get_data_owner())
        if account.is_system:
            messages.error(request, "System account ma tirtiri karto.")
            return redirect("web-account-list")
        has_transactions = JournalEntryLine.objects.filter(account=account).exists()
        if has_transactions:
            messages.error(request, f"Account '{account.name}' waxa leh transactions - marka bedel (deactivate) markii hore.")
            return redirect("web-account-list")
        return render(request, "web/confirm_delete.html", {"object": account, "cancel_url": "web-account-list"})

    def post(self, request, pk):
        account = get_object_or_404(Account, pk=pk, owner=request.user.get_data_owner())
        if account.is_system:
            messages.error(request, "System account ma tirtiri karto.")
            return redirect("web-account-list")
        has_transactions = JournalEntryLine.objects.filter(account=account).exists()
        if has_transactions:
            messages.error(request, f"Account '{account.name}' waxa leh transactions - marka bedel (deactivate) markii hore.")
            return redirect("web-account-list")
        account.delete()
        return redirect("web-account-list")


# ── Journal Entries ───────────────────────────────────────────────────────────

class JournalEntryListView(HomeView):
    template_name = "web/journal_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["entries"] = JournalEntry.objects.filter(owner=self.request.user.get_data_owner()).select_related("tenant")
        return context


class JournalEntryDetailView(LoginRequiredMixin, DetailView):
    model = JournalEntry
    template_name = "web/journal_detail.html"
    context_object_name = "entry"
    login_url = "/login/"

    def get_queryset(self):
        return JournalEntry.objects.filter(owner=self.request.user.get_data_owner()).select_related("tenant")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("account", "property")
        return context


class JournalEntryCreateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        form = JournalEntryForm(user=request.user.get_data_owner())
        formset = JournalEntryLineFormSet(user=request.user.get_data_owner())
        return render(request, "web/journal_form.html", {"form": form, "formset": formset})

    def post(self, request):
        form = JournalEntryForm(request.POST, user=request.user.get_data_owner())
        formset = JournalEntryLineFormSet(request.POST, user=request.user.get_data_owner())
        if form.is_valid() and formset.is_valid():
            entry = form.save(commit=False)
            entry.owner = request.user.get_data_owner()
            entry.save()
            formset.instance = entry
            formset.save()
            return redirect("web-journal-detail", entry.pk)
        return render(request, "web/journal_form.html", {"form": form, "formset": formset})


class JournalEntryUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk, owner=request.user.get_data_owner())
        form = JournalEntryForm(instance=entry, user=request.user.get_data_owner())
        formset = JournalEntryLineFormSet(instance=entry, user=request.user.get_data_owner())
        return render(request, "web/journal_form.html", {"form": form, "formset": formset, "editing": True})

    def post(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk, owner=request.user.get_data_owner())
        form = JournalEntryForm(request.POST, instance=entry, user=request.user.get_data_owner())
        formset = JournalEntryLineFormSet(request.POST, instance=entry, user=request.user.get_data_owner())
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect("web-journal-detail", pk)
        return render(request, "web/journal_form.html", {"form": form, "formset": formset, "editing": True})


class JournalEntryDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk, owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": entry, "cancel_url": "web-journal-list"})

    def post(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk, owner=request.user.get_data_owner())
        entry.delete()
        return redirect("web-journal-list")


# ── Invoices ──────────────────────────────────────────────────────────────────

class InvoiceListView(HomeView):
    template_name = "web/invoice_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invoices"] = Invoice.objects.filter(owner=self.request.user.get_data_owner()).select_related("tenant", "property")
        return context


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = "web/invoice_detail.html"
    context_object_name = "invoice"
    login_url = "/login/"

    def get_queryset(self):
        return Invoice.objects.filter(owner=self.request.user.get_data_owner()).select_related("tenant", "property", "rental_agreement")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("account")
        context["total"] = self.object.get_total_amount()
        return context


class InvoiceCreateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        form = InvoiceForm(user=request.user.get_data_owner())
        formset = InvoiceLineFormSet(user=request.user.get_data_owner())
        return render(request, "web/invoice_form.html", {"form": form, "formset": formset})

    def post(self, request):
        form = InvoiceForm(request.POST, user=request.user.get_data_owner())
        formset = InvoiceLineFormSet(request.POST, user=request.user.get_data_owner())
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            invoice.owner = request.user.get_data_owner()
            # Save invoice first (so formset has an instance), then lines, then re-post
            invoice.save()
            formset.instance = invoice
            formset.save()
            # Ensure journal entry is created now that lines exist
            from accounting.services import post_invoice
            post_invoice(invoice)
            return redirect("web-invoice-detail", invoice.pk)
        return render(request, "web/invoice_form.html", {"form": form, "formset": formset})


class InvoiceUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, owner=request.user.get_data_owner())
        form = InvoiceForm(instance=invoice, user=request.user.get_data_owner())
        formset = InvoiceLineFormSet(instance=invoice, user=request.user.get_data_owner())
        return render(request, "web/invoice_form.html", {"form": form, "formset": formset, "editing": True})

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, owner=request.user.get_data_owner())
        form = InvoiceForm(request.POST, instance=invoice, user=request.user.get_data_owner())
        formset = InvoiceLineFormSet(request.POST, instance=invoice, user=request.user.get_data_owner())
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            # Re-post journal entry with updated lines
            from accounting.services import post_invoice
            post_invoice(invoice)
            return redirect("web-invoice-detail", pk)
        return render(request, "web/invoice_form.html", {"form": form, "formset": formset, "editing": True})


class InvoiceDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": invoice, "cancel_url": "web-invoice-list"})

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, owner=request.user.get_data_owner())
        invoice.delete()
        return redirect("web-invoice-list")


# ── Bank Accounts ────────────────────────────────────────────────────────────

class BankAccountListView(HomeView):
    template_name = "web/bank_account_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        owner = self.request.user.get_data_owner()
        bank_accounts = BankAccount.objects.filter(owner=owner)
        for ba in bank_accounts:
            if ba.linked_account:
                from django.db.models import Sum
                lines = JournalEntryLine.objects.filter(
                    account=ba.linked_account,
                    journal_entry__status="posted"
                )
                dr = lines.aggregate(t=Sum("debit"))["t"] or 0
                cr = lines.aggregate(t=Sum("credit"))["t"] or 0
                ba.balance = float(dr - cr)
            else:
                ba.balance = None
        context["bank_accounts"] = bank_accounts
        return context


class BankAccountDetailView(LoginRequiredMixin, DetailView):
    model = BankAccount
    template_name = "web/bank_account_detail.html"
    context_object_name = "bank_account"
    login_url = "/login/"

    def get_queryset(self):
        return BankAccount.objects.filter(owner=self.request.user.get_data_owner())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        bank = self.object

        payments = Payment.objects.filter(bank_account=bank).select_related(
            "rental_agreement__tenant", "rental_agreement__property"
        ).order_by("-payment_date")
        expenses = GeneralExpense.objects.filter(bank_account=bank).select_related("property").order_by("-expense_date")
        repairs = MaintenanceRepair.objects.filter(bank_account=bank).select_related("property").order_by("-reported_date")

        context["payments"] = payments[:20]
        context["expenses"] = expenses[:20]
        context["repairs"] = repairs[:20]

        all_txns = []
        total_in = 0
        total_out = 0

        for p in payments:
            tenant = p.rental_agreement.tenant
            prop = p.rental_agreement.property
            amount = float(p.amount)
            total_in += amount
            all_txns.append({
                "date": p.payment_date,
                "type": "in",
                "description": f"Lacag ka timid {tenant.full_name}",
                "detail": f"{prop.name} — REF: {p.reference}",
                "amount": amount,
                "sort_date": p.payment_date,
            })

        for e in expenses:
            prop = e.property
            amount = float(e.amount)
            total_out += amount
            all_txns.append({
                "date": e.expense_date,
                "type": "out",
                "description": f"Kharash: {e.title}",
                "detail": f"{prop.name} — REF: {e.reference}",
                "amount": amount,
                "sort_date": e.expense_date,
            })

        for r in repairs:
            prop = r.property
            amount = float(r.cost)
            total_out += amount
            all_txns.append({
                "date": r.reported_date,
                "type": "out",
                "description": f"Dayactir: {r.title}",
                "detail": f"{prop.name} — REF: {r.reference}",
                "amount": amount,
                "sort_date": r.reported_date,
            })

        all_txns.sort(key=lambda x: x["sort_date"])

        context["all_transactions"] = all_txns
        context["total_in"] = total_in
        context["total_out"] = total_out
        context["balance"] = total_in - total_out
        return context


class BankAccountCreateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        form = BankAccountForm()
        return render(request, "web/bank_account_form.html", {"form": form})

    def post(self, request):
        form = BankAccountForm(request.POST)
        if form.is_valid():
            bank = form.save(commit=False)
            bank.owner = request.user.get_data_owner()
            bank.save()
            link_bank_account_to_ledger(bank)
            return redirect("web-bank-accounts")
        return render(request, "web/bank_account_form.html", {"form": form})


class BankAccountUpdateView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        bank = get_object_or_404(BankAccount, pk=pk, owner=request.user.get_data_owner())
        form = BankAccountForm(instance=bank)
        return render(request, "web/bank_account_form.html", {"form": form, "editing": True})

    def post(self, request, pk):
        bank = get_object_or_404(BankAccount, pk=pk, owner=request.user.get_data_owner())
        form = BankAccountForm(request.POST, instance=bank)
        if form.is_valid():
            form.save()
            return redirect("web-bank-accounts")
        return render(request, "web/bank_account_form.html", {"form": form, "editing": True})


class BankAccountDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request, pk):
        bank = get_object_or_404(BankAccount, pk=pk, owner=request.user.get_data_owner())
        return render(request, "web/confirm_delete.html", {"object": bank, "cancel_url": "web-bank-accounts"})

    def post(self, request, pk):
        bank = get_object_or_404(BankAccount, pk=pk, owner=request.user.get_data_owner())
        bank.delete()
        return redirect("web-bank-accounts")


# ── AI Chatbot ────────────────────────────────────────────────────────────────

class ChatbotView(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        from finance.models import ChatSession, ChatMessage
        owner = request.user.get_data_owner()
        sessions = ChatSession.objects.filter(owner=owner)
        session_id = request.GET.get("session")
        messages = []
        active_session = None

        if session_id:
            active_session = sessions.filter(pk=session_id).first()
            if active_session:
                messages = ChatMessage.objects.filter(session=active_session)
        elif sessions.exists():
            active_session = sessions.first()
            messages = ChatMessage.objects.filter(session=active_session)

        return render(request, "web/chatbot.html", {
            "sessions": sessions,
            "active_session": active_session,
            "messages": messages,
        })

    def post(self, request):
        from .chatbot import ask_ai
        from finance.models import ChatSession, ChatMessage

        owner = request.user.get_data_owner()
        question = request.POST.get("question", "").strip()
        session_id = request.POST.get("session_id")

        if not question:
            return JsonResponse({"error": "Please type a question."}, status=400)

        # Get or create session
        if session_id:
            session = ChatSession.objects.filter(pk=session_id, owner=owner).first()
        else:
            session = None

        if not session:
            title = question[:60] + ("..." if len(question) > 60 else "")
            session = ChatSession.objects.create(owner=owner, title=title)

        # Save user message
        ChatMessage.objects.create(session=session, role="user", content=question)

        # Get AI answer
        answer = ask_ai(owner, question)

        # Save AI response
        ChatMessage.objects.create(session=session, role="ai", content=answer)

        return JsonResponse({"answer": answer, "session_id": session.id})


class ChatSessionDeleteView(LoginRequiredMixin, View):
    login_url = "/login/"

    def post(self, request, pk):
        from finance.models import ChatSession
        owner = request.user.get_data_owner()
        session = get_object_or_404(ChatSession, pk=pk, owner=owner)
        session.delete()
        return redirect("web-chatbot")
