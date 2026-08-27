from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class UserAdminConfiguration(UserAdmin):
    model = User
    ordering = ("phone_number",)
    list_display = ("username", "phone_number", "full_name", "is_approved", "is_staff", "is_active")
    search_fields = ("username", "phone_number", "full_name")
    fieldsets = ((None, {"fields": ("username", "phone_number", "password")}), ("Macluumaadka qofka", {"fields": ("full_name",)}), ("Ogolaanshaha", {"fields": ("is_approved", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}))
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("username", "phone_number", "full_name", "password1", "password2", "is_staff", "is_active")} ),)
