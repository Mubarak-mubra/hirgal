from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Property, PropertyAsset, Room, Unit


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "property_type", "residential_structure", "location", "cover_image")
    list_filter = ("property_type", "residential_structure")
    search_fields = ("name", "location", "owner__phone_number")


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("unit_number", "property", "floor_number", "unit_type", "rental_mode", "monthly_rent")
    list_filter = ("unit_type",)
    search_fields = ("unit_number", "property__name")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("room_name", "room_type", "unit", "monthly_rent")
    search_fields = ("room_name", "unit__unit_number", "unit__property__name")


@admin.register(PropertyAsset)
class PropertyAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "property", "quantity", "condition", "responsible_party")
    list_filter = ("condition", "responsible_party")
    search_fields = ("name", "property__name")
