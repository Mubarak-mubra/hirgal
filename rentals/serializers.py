from rest_framework import serializers
from .models import Tenant, RentalAgreement


class RentalAgreementSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source="property.name", read_only=True)
    unit_number = serializers.CharField(source="unit.unit_number", read_only=True, default=None)

    class Meta:
        model = RentalAgreement
        fields = [
            "id",
            "tenant",
            "property",
            "property_name",
            "unit",
            "unit_number",
            "agreed_monthly_rent",
            "monthly_rent",
            "security_deposit",
            "start_date",
            "end_date",
            "status",
        ]


class TenantSerializer(serializers.ModelSerializer):
    rental_agreements = RentalAgreementSerializer(many=True, read_only=True)

    class Meta:
        model = Tenant
        fields = [
            "id",
            "full_name",
            "phone_number",
            "emergency_contact",
            "notes",
            "rental_agreements",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class TenantRegistrationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=20)
    property_id = serializers.IntegerField()
    unit_id = serializers.IntegerField(required=False, allow_null=True)
    agreed_monthly_rent = serializers.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    start_date = serializers.DateField()

    def create(self, validated_data):
        user = self.context["request"].user
        tenant = Tenant.objects.create(
            owner=user,
            full_name=validated_data["full_name"],
            phone_number=validated_data["phone_number"],
        )
        RentalAgreement.objects.create(
            tenant=tenant,
            property_id=validated_data["property_id"],
            unit_id=validated_data.get("unit_id"),
            agreed_monthly_rent=validated_data["agreed_monthly_rent"],
            monthly_rent=validated_data["agreed_monthly_rent"],
            security_deposit=validated_data.get("security_deposit", 0),
            start_date=validated_data["start_date"],
            status="active",
        )
        return tenant
