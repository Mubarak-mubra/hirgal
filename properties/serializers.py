from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from .models import Property, Room, Unit


class PropertySerializer(serializers.ModelSerializer):
    total_rentable_spaces = serializers.IntegerField(required=False, default=1)
    total_units = serializers.SerializerMethodField()
    rented_units = serializers.SerializerMethodField()
    available_units = serializers.SerializerMethodField()
    expected_monthly_rent = serializers.SerializerMethodField()
    collected_monthly_rent = serializers.SerializerMethodField()
    monthly_expenses = serializers.SerializerMethodField()
    missing_monthly_rent = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = ("id", "name", "property_type", "location", "total_rentable_spaces", "cover_image", "description", "total_units", "rented_units", "available_units", "expected_monthly_rent", "collected_monthly_rent", "monthly_expenses", "missing_monthly_rent")
        read_only_fields = ("id", "total_units", "rented_units", "available_units", "expected_monthly_rent")

    def get_available_units(self, property_instance):
        return self.get_total_units(property_instance) - self.get_rented_units(property_instance)

    def get_total_units(self, property_instance):
        return property_instance.total_rentable_spaces

    def get_rented_units(self, property_instance):
        agreements = property_instance.rental_agreements.filter(status="active")
        if agreements.filter(rental_scope="whole_property").exists():
            return property_instance.total_rentable_spaces
        return agreements.aggregate(total=Sum("rented_space_count"))["total"] or 0

    def get_expected_monthly_rent(self, property_instance):
        if hasattr(property_instance, "expected_monthly_rent") and property_instance.expected_monthly_rent:
            return property_instance.expected_monthly_rent
        agreement_total = property_instance.rental_agreements.filter(status="active").aggregate(total=Sum("agreed_monthly_rent"))["total"]
        if agreement_total:
            return agreement_total
        return property_instance.units.aggregate(total=Sum("monthly_rent"))["total"] or 0

    def get_collected_monthly_rent(self, property_instance):
        today = timezone.localdate()
        return property_instance.rental_agreements.filter(status="active", payments__payment_date__year=today.year, payments__payment_date__month=today.month).aggregate(total=Sum("payments__amount"))["total"] or 0

    def get_monthly_expenses(self, property_instance):
        today = timezone.localdate()
        return property_instance.general_expenses.filter(expense_date__year=today.year, expense_date__month=today.month).aggregate(total=Sum("amount"))["total"] or 0

    def get_missing_monthly_rent(self, property_instance):
        return max(self.get_expected_monthly_rent(property_instance) - self.get_collected_monthly_rent(property_instance), 0)


class UnitSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source="property.name", read_only=True)

    class Meta:
        model = Unit
        fields = ("id", "property", "property_name", "unit_number", "unit_type", "total_rooms", "bathrooms", "living_rooms", "rental_mode", "monthly_rent")
        read_only_fields = ("id", "property", "property_name")


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ("id", "unit", "room_name", "monthly_rent")
        read_only_fields = ("id", "unit")
