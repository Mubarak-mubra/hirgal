from rest_framework import serializers
from .models import Property, Unit, Room, PropertyAsset


class PropertySerializer(serializers.ModelSerializer):
    total_units = serializers.IntegerField(read_only=True, default=0)
    rented_units = serializers.IntegerField(read_only=True, default=0)
    expected_monthly_rent = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=0)

    class Meta:
        model = Property
        fields = [
            "id",
            "name",
            "property_type",
            "residential_structure",
            "location",
            "total_rentable_spaces",
            "cover_image",
            "description",
            "total_units",
            "rented_units",
            "expected_monthly_rent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class UnitSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source="property.name", read_only=True)

    class Meta:
        model = Unit
        fields = [
            "id",
            "property",
            "property_name",
            "floor_number",
            "unit_number",
            "unit_type",
            "total_rooms",
            "bathrooms",
            "living_rooms",
            "rental_mode",
            "monthly_rent",
        ]
        read_only_fields = ["id", "property"]


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = [
            "id",
            "unit",
            "room_type",
            "room_name",
            "monthly_rent",
        ]
        read_only_fields = ["id", "unit"]


class PropertyAssetSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source="property.name", read_only=True)

    class Meta:
        model = PropertyAsset
        fields = [
            "id",
            "property",
            "property_name",
            "name",
            "quantity",
            "condition",
            "responsible_party",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
