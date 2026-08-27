from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Property, Room, Unit


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "property_type", "location", "cover_image")
    list_filter = ("property_type",)
    search_fields = ("name", "location", "owner__phone_number")


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("unit_number", "property", "unit_type", "rental_mode", "monthly_rent")
    list_filter = ("unit_type",)
    search_fields = ("unit_number", "property__name")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("room_name", "unit", "monthly_rent")
    search_fields = ("room_name", "unit__unit_number", "unit__property__name")
