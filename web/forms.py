from django import forms
from django.contrib.auth import get_user_model

from accounting.models import Account, Invoice, InvoiceLine, JournalEntry, JournalEntryLine
from finance.models import BankAccount, GeneralExpense, MaintenanceRepair, Payment
from properties.models import Property, PropertyAsset, Room, Unit
from rentals.models import RentalAgreement, Tenant

User = get_user_model()

FORM_INPUT = "mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:bg-white focus:ring-4 focus:ring-indigo-100"
FORM_SELECT = "mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:bg-white focus:ring-4 focus:ring-indigo-100"


def _style_fields(form):
    for field in form.fields.values():
        if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
            field.widget.attrs["class"] = FORM_SELECT
        else:
            field.widget.attrs["class"] = FORM_INPUT


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("username", "phone_number", "full_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("full_name", "phone_number")
        labels = {
            "full_name": "Full Name",
            "phone_number": "Phone Number",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = ("name", "property_type", "residential_structure", "location", "electricity_account_no", "water_account_no", "description")
        labels = {
            "name": "Property Name",
            "property_type": "Property Type",
            "residential_structure": "Structure Type",
            "location": "Location",
            "description": "Description",
            "electricity_account_no": "Electricity Account No.",
            "water_account_no": "Water Account No.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
        self.fields["description"].widget.attrs["rows"] = 4


class PropertyAssetForm(forms.ModelForm):
    class Meta:
        model = PropertyAsset
        fields = ("name", "quantity", "condition", "responsible_party", "notes")
        labels = {
            "name": "Item Name",
            "quantity": "Quantity",
            "condition": "Condition",
            "responsible_party": "Responsible Party",
            "notes": "Notes",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
        self.fields["notes"].widget.attrs["rows"] = 4


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ("floor_number", "unit_number", "unit_type", "total_rooms", "bathrooms", "living_rooms", "rental_mode")
        labels = {
            "floor_number": "Floor Number",
            "unit_number": "Unit Number",
            "unit_type": "Unit Type",
            "total_rooms": "Total Rooms",
            "bathrooms": "Bathrooms",
            "living_rooms": "Living Rooms",
            "rental_mode": "Rental Mode",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ("room_type", "room_name")
        labels = {
            "room_type": "Room Type",
            "room_name": "Room Name",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class VillaDetailsForm(forms.Form):
    total_rooms = forms.IntegerField(min_value=1, label="Total Rooms")
    bathrooms = forms.IntegerField(min_value=1, label="Bathrooms")
    living_rooms = forms.IntegerField(min_value=1, label="Living Rooms")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ("full_name", "tenant_type", "phone_number", "notes")
        labels = {
            "full_name": "Full Name",
            "tenant_type": "Tenant Type",
            "phone_number": "Phone Number",
            "notes": "Notes",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
        self.fields["notes"].widget.attrs["rows"] = 3


class RentalAgreementForm(forms.ModelForm):
    class Meta:
        model = RentalAgreement
        fields = ("tenant", "property", "unit", "room", "monthly_rent", "start_date", "end_date", "status",
                  "electricity_responsible", "water_responsible", "final_bills_settlement", "final_bills_notes", "notes")
        labels = {
            "tenant": "Tenant", "property": "Property", "unit": "Unit", "room": "Room",
            "monthly_rent": "Monthly Rent ($)",
            "start_date": "Start Date", "end_date": "End Date",
            "status": "Status", "notes": "Notes",
            "electricity_responsible": "Electricity paid by",
            "water_responsible": "Water paid by",
            "final_bills_settlement": "Final electricity/water bills",
            "final_bills_notes": "Settlement notes",
        }
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, tenant_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            from django.db.models import Q
            active_agreements = RentalAgreement.objects.filter(status="active")

            # Properties that are fully rented (whole property agreement)
            fully_rented_property_ids = active_agreements.filter(
                rental_scope="whole_property"
            ).values_list("property_id", flat=True)

            # Get available properties (not fully rented)
            available_properties = Property.objects.filter(owner=user).exclude(
                id__in=fully_rented_property_ids
            )

            # For each property, check if it has units
            # If property has units, check if all units are rented
            final_property_ids = []
            for prop in available_properties:
                units = prop.units.all()
                if not units.exists():
                    # No units = whole property rental, include if not fully rented
                    final_property_ids.append(prop.pk)
                else:
                    # Has units - check if any unit is available
                    rented_unit_ids = active_agreements.filter(
                        property=prop
                    ).values_list("unit_id", flat=True)
                    available_units = units.exclude(id__in=rented_unit_ids)
                    if available_units.exists():
                        final_property_ids.append(prop.pk)

            self.fields["tenant"].queryset = Tenant.objects.filter(owner=user)
            self.fields["property"].queryset = Property.objects.filter(id__in=final_property_ids)
            self.fields["unit"].queryset = Unit.objects.none()
            self.fields["room"].queryset = Room.objects.none()

            if tenant_id:
                self.fields["tenant"].initial = tenant_id
                self.fields["tenant"].widget.attrs["readonly"] = True
                self.fields["tenant"].widget.attrs["class"] = "bg-slate-100 cursor-not-allowed"

        _style_fields(self)
        self.fields["notes"].widget.attrs["rows"] = 3

    def clean(self):
        cleaned_data = super().clean()
        tenant = cleaned_data.get("tenant")
        property_obj = cleaned_data.get("property")
        unit = cleaned_data.get("unit")
        status = cleaned_data.get("status")

        if tenant and property_obj and status == "active":
            existing = RentalAgreement.objects.filter(
                tenant=tenant,
                property=property_obj,
                status="active",
            )
            if unit:
                existing = existing.filter(unit=unit)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError("This tenant already has an active agreement for this property.")

        return cleaned_data


class PaymentForm(forms.ModelForm):
    tenant = forms.ModelChoiceField(
        queryset=Tenant.objects.none(),
        required=False,
        label="Tenant",
        widget=forms.Select(attrs={"id": "id_tenant_select"}),
    )
    invoice = forms.ModelChoiceField(
        queryset=Invoice.objects.none(),
        required=False,
        label="Invoice (optional)",
        empty_label="No invoice",
    )

    class Meta:
        model = Payment
        fields = ("rental_agreement", "amount", "payment_date", "payment_method", "bank_account", "destination_account", "invoice", "reference_number", "notes")
        labels = {
            "rental_agreement": "Agreement", "amount": "Amount", "payment_date": "Date",
            "payment_method": "Payment Method", "bank_account": "Bank Account",
            "destination_account": "Destination Account (optional)",
            "reference_number": "Reference (auto-generated, can edit)", "notes": "Notes",
        }
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["tenant"].queryset = Tenant.objects.filter(owner=user)
            self.fields["rental_agreement"].queryset = RentalAgreement.objects.filter(
                tenant__owner=user, status="active"
            )
            self.fields["bank_account"].queryset = BankAccount.objects.filter(owner=user)
            self.fields["destination_account"].queryset = Account.objects.filter(owner=user, category="asset")
            self.fields["invoice"].queryset = Invoice.objects.filter(
                owner=user, status__in=["sent", "draft"]
            ).order_by("-date")

        # Auto-generate reference number if creating new payment
        if not self.instance.pk:
            self.fields["reference_number"].initial = self._generate_reference(user)

        _style_fields(self)
        self.fields["notes"].widget.attrs["rows"] = 3

    def _generate_reference(self, user):
        """Generate a unique reference like PAY-2026-0001"""
        from datetime import date
        today = date.today()
        year = today.year
        prefix = f"PAY-{year}-"

        # Count payments this year
        from finance.models import Payment
        count = Payment.objects.filter(
            rental_agreement__tenant__owner=user,
            created_at__year=year,
        ).count()

        return f"{prefix}{count + 1:04d}"


class MaintenanceRepairForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRepair
        fields = ("property", "unit", "title", "description", "category", "status", "repair_cost", "payment_status", "expense_account", "bank_account", "reported_date", "fixed_date", "notes")
        labels = {
            "property": "Property", "unit": "Unit (optional)",
            "title": "Title", "description": "Description",
            "category": "Category", "status": "Status", "repair_cost": "Repair Cost ($)",
            "payment_status": "Payment Status",
            "expense_account": "Expense Account (optional)",
            "bank_account": "Bank Account",
            "reported_date": "Reported Date", "fixed_date": "Fixed Date",
            "notes": "Additional Notes",
        }
        widgets = {
            "reported_date": forms.DateInput(attrs={"type": "date"}),
            "fixed_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["property"].queryset = Property.objects.filter(owner=user)
            self.fields["unit"].queryset = Unit.objects.filter(property__owner=user)
            self.fields["expense_account"].queryset = Account.objects.filter(owner=user, category="expense")
            self.fields["bank_account"].queryset = BankAccount.objects.filter(owner=user)
        _style_fields(self)
        self.fields["description"].widget.attrs["rows"] = 3
        self.fields["notes"].widget.attrs["rows"] = 3


class GeneralExpenseForm(forms.ModelForm):
    class Meta:
        model = GeneralExpense
        fields = ("property", "title", "category", "amount", "payment_status", "expense_account", "bank_account", "expense_date", "notes")
        labels = {
            "property": "Property", "title": "Title", "category": "Category",
            "amount": "Amount ($)", "payment_status": "Payment Status",
            "expense_account": "Expense Account (optional)",
            "bank_account": "Bank Account",
            "expense_date": "Date", "notes": "Notes",
        }
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["property"].queryset = Property.objects.filter(owner=user)
            self.fields["expense_account"].queryset = Account.objects.filter(owner=user, category="expense")
            self.fields["bank_account"].queryset = BankAccount.objects.filter(owner=user)
        _style_fields(self)
        self.fields["notes"].widget.attrs["rows"] = 3


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ("code", "name", "category", "bank_account", "description", "is_active")
        labels = {
            "code": "Account Code",
            "name": "Account Name",
            "category": "Category",
            "bank_account": "Linked Bank Account (optional)",
            "description": "Description (optional)",
            "is_active": "Active",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["bank_account"].queryset = BankAccount.objects.filter(owner=user)
        _style_fields(self)
        self.fields["description"].widget.attrs["rows"] = 2
        if self.instance and self.instance.pk and self.instance.is_system:
            self.fields["code"].disabled = True
            self.fields["name"].disabled = True
            self.fields["category"].disabled = True

    def clean_code(self):
        code = self.cleaned_data.get("code")
        category = self.cleaned_data.get("category")
        if not code or not category:
            return code
        from accounting.models import CODE_RANGES
        lo, hi = CODE_RANGES.get(category, (0, 0))
        try:
            code_int = int(code)
        except ValueError:
            raise forms.ValidationError("Code must be a number.")
        if not (lo <= code_int <= hi):
            raise forms.ValidationError(f"Code {code} is not valid for {category}. Valid range: {lo} - {hi}")
        user = self.initial.get("user") or (self.instance.owner if self.instance.pk else None)
        if user:
            qs = Account.objects.filter(owner=user, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"Code {code} is already in use.")
        return code

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.pk and self.instance.is_system:
            for field in ["name", "category"]:
                if cleaned_data.get(field) != getattr(self.instance, field):
                    self.add_error(field, "System accounts cannot be modified.")
        return cleaned_data


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ("bank_name", "account_number", "account_name", "notes", "is_active")
        labels = {
            "bank_name": "Bank Name",
            "account_number": "Account Number",
            "account_name": "Account Name",
            "notes": "Notes",
            "is_active": "Active",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
        self.fields["notes"].widget.attrs["rows"] = 2


class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ("date", "reference", "description", "status", "tenant")
        labels = {
            "date": "Date",
            "reference": "Reference",
            "description": "Description",
            "status": "Status",
            "tenant": "Tenant (optional)",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["tenant"].queryset = Tenant.objects.filter(owner=user)
        _style_fields(self)
        self.fields["description"].widget.attrs["rows"] = 3


class JournalEntryLineForm(forms.ModelForm):
    class Meta:
        model = JournalEntryLine
        fields = ("account", "description", "debit", "credit", "property")
        labels = {
            "account": "Account",
            "description": "Description",
            "debit": "Debit ($)",
            "credit": "Credit ($)",
            "property": "Property (optional)",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["account"].queryset = Account.objects.filter(owner=user)
            self.fields["property"].queryset = Property.objects.filter(owner=user)
        _style_fields(self)


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ("tenant", "rental_agreement", "property", "invoice_number", "date", "due_date", "status", "notes")
        labels = {
            "tenant": "Tenant", "rental_agreement": "Rental Agreement", "property": "Property",
            "invoice_number": "Invoice Number", "date": "Invoice Date", "due_date": "Due Date",
            "status": "Status", "notes": "Notes",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["tenant"].queryset = Tenant.objects.filter(owner=user)
            self.fields["rental_agreement"].queryset = RentalAgreement.objects.filter(tenant__owner=user, status="active")
            self.fields["property"].queryset = Property.objects.filter(owner=user)
        _style_fields(self)
        self.fields["notes"].widget.attrs["rows"] = 3

        if not self.instance.pk:
            self.fields["invoice_number"].initial = self._generate_invoice_number(user)

    def _generate_invoice_number(self, user):
        from datetime import date
        today = date.today()
        year = today.year
        prefix = "INV-%s-" % year
        count = Invoice.objects.filter(owner=user, date__year=year).count()
        return "%s%04d" % (prefix, count + 1)


class InvoiceLineForm(forms.ModelForm):
    class Meta:
        model = InvoiceLine
        fields = ("account", "description", "amount")
        labels = {
            "account": "Revenue Account",
            "description": "Description",
            "amount": "Amount ($)",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["account"].queryset = Account.objects.filter(owner=user, category="revenue")
        _style_fields(self)


class UserFormSetMixin:
    """Mixin that passes user to each form in the formset."""
    user = None

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs["user"] = self.user
        return super()._construct_form(i, **kwargs)


class JournalEntryLineFormSet(UserFormSetMixin, forms.BaseInlineFormSet):
    pass


class InvoiceLineFormSetClass(UserFormSetMixin, forms.BaseInlineFormSet):
    pass


JournalEntryLineFormSet = forms.inlineformset_factory(
    JournalEntry, JournalEntryLine, form=JournalEntryLineForm,
    formset=JournalEntryLineFormSet, extra=1, can_delete=True,
)
InvoiceLineFormSet = forms.inlineformset_factory(
    Invoice, InvoiceLine, form=InvoiceLineForm,
    formset=InvoiceLineFormSetClass, extra=1, can_delete=True,
)
