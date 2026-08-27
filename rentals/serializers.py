from django.utils import timezone
from django.db.models import Avg, Sum
from django.db import transaction
from rest_framework import serializers

from properties.models import Property, Unit
from .models import RentalAgreement, Tenant


class TenantSerializer(serializers.ModelSerializer):
    property_name = serializers.SerializerMethodField()
    unit_name = serializers.SerializerMethodField()
    rent = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    average_payment = serializers.SerializerMethodField()
    payment_quality = serializers.SerializerMethodField()
    agreements = serializers.SerializerMethodField()
    class Meta:
        model = Tenant
        fields = ("id", "full_name", "tenant_type", "phone_number", "notes", "property_name", "unit_name", "rent", "status", "agreements", "average_payment", "payment_quality")

    def get_agreement(self, tenant):
        return tenant.rental_agreements.filter(status="active").select_related("property", "unit").first()

    def get_property_name(self, tenant):
        agreement = self.get_agreement(tenant)
        return agreement.property.name if agreement and agreement.property else agreement.unit.property.name if agreement and agreement.unit else ""

    def get_unit_name(self, tenant):
        agreement = self.get_agreement(tenant)
        if not agreement:
            return ""
        if agreement.unit:
            return agreement.unit.unit_number
        if agreement.rental_scope == "partial_property":
            space_label = "qolal" if agreement.property and agreement.property.property_type == "home" else "qaybood"
            return f"{agreement.rented_space_count} {space_label}"
        return "Hantida oo dhan"

    def get_rent(self, tenant):
        agreement = self.get_agreement(tenant)
        return agreement.agreed_monthly_rent if agreement else 0

    def get_status(self, tenant):
        agreement = self.get_agreement(tenant)
        if not agreement:
            return "unpaid"
        today = timezone.localdate()
        total_paid = agreement.payments.filter(payment_date__year=today.year, payment_date__month=today.month).aggregate(total=Sum("amount"))["total"] or 0
        if total_paid >= agreement.agreed_monthly_rent:
            return "paid"
        if today.day >= 5:
            return "overdue"
        return "partial" if total_paid > 0 else "unpaid"

    def get_agreements(self, tenant):
        return [{"property": agreement.property.name if agreement.property else "", "rent": agreement.agreed_monthly_rent, "status": agreement.status} for agreement in tenant.rental_agreements.select_related("property").all()]

    def get_average_payment(self, tenant):
        return tenant.rental_agreements.filter(payments__isnull=False).aggregate(average=Avg("payments__amount"))["average"] or 0

    def get_payment_quality(self, tenant):
        return {"paid": "Aad u fiican", "partial": "Dhexdhexaad", "unpaid": "Dhibaato badan", "overdue": "Daahitaan badan"}.get(self.get_status(tenant), "Lama qiimeyn")


class TenantRegistrationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    property_id = serializers.IntegerField()
    unit_id = serializers.IntegerField(required=False, allow_null=True)
    rental_scope = serializers.ChoiceField(choices=["whole_property", "partial_property"])
    rented_space_count = serializers.IntegerField(min_value=1)
    agreed_monthly_rent = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attributes):
        owner = self.context["request"].user
        try:
            property_instance = Property.objects.get(
                id=attributes["property_id"], owner=owner
            )
        except Property.DoesNotExist:
            raise serializers.ValidationError({"property_id": "Hantidan lama helin."})

        requested_spaces = attributes["rented_space_count"]
        active_agreements = RentalAgreement.objects.filter(
            property=property_instance, status="active"
        )
        if attributes["rental_scope"] == "whole_property":
            if active_agreements.exists():
                raise serializers.ValidationError(
                    {"property_id": "Hantidan hore ayaa loo wada kiraystay."}
                )
        else:
            used_spaces = sum(
                agreement.rented_space_count for agreement in active_agreements
            )
            available_spaces = property_instance.total_rentable_spaces - used_spaces
            if requested_spaces > available_spaces:
                raise serializers.ValidationError(
                    {"rented_space_count": f"Kaliya {max(available_spaces, 0)} qayb ayaa bannaan."}
                )
        return attributes

    def create(self, validated_data):
        owner = self.context["request"].user
        property_instance = Property.objects.get(id=validated_data.pop("property_id"), owner=owner)
        unit_id = validated_data.pop("unit_id", None)
        unit = Unit.objects.get(id=unit_id, property=property_instance) if unit_id else None
        if validated_data["rental_scope"] == "whole_property":
            validated_data["rented_space_count"] = property_instance.total_rentable_spaces
        with transaction.atomic():
            full_name = validated_data.pop("full_name")
            phone_number = validated_data.pop("phone_number", None) or None
            tenant, created = Tenant.objects.get_or_create(owner=owner, phone_number=phone_number, defaults={"full_name": full_name})
            if not created and tenant.full_name != full_name:
                tenant.full_name = full_name
                tenant.save(update_fields=["full_name", "updated_at"])
            agreed_rent = validated_data["agreed_monthly_rent"]
            RentalAgreement.objects.create(tenant=tenant, property=property_instance, unit=unit, monthly_rent=agreed_rent, **validated_data)
        return tenant

    def to_representation(self, instance):
        return TenantSerializer(instance).data
