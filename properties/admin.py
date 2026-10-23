from django.contrib import admin

# Register your models here.
from .models import ExploreSettings, Property, PropertyAsset, PropertyType, Room, Unit


@admin.register(ExploreSettings)
class ExploreSettingsAdmin(admin.ModelAdmin):
    list_display = ("whatsapp_number", "contact_phone", "contact_email", "contact_address", "updated_at")

    def has_add_permission(self, request):
        return not ExploreSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PropertyType)
class PropertyTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "has_units", "created_at")
    list_filter = ("has_units",)
    search_fields = ("name", "owner__phone_number")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "property_type", "location", "cover_image")
    list_filter = ("property_type",)
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
