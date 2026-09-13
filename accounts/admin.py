from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, SiteSettings


@admin.action(description="Ancixi isticmaalayaasha la doortay (Approve selected users)")
def approve_users(modeladmin, request, queryset):
    queryset.update(is_approved=True)


@admin.action(description="Ka noqo ansixinta (Unapprove selected users)")
def unapprove_users(modeladmin, request, queryset):
    queryset.update(is_approved=False)


@admin.action(description="Sii ogolaanshaha Admin-ka (Grant Staff Access)")
def make_staff(modeladmin, request, queryset):
    queryset.update(is_staff=True)


@admin.register(User)
class UserAdminConfiguration(UserAdmin):
    model = User
    ordering = ("username",)
    list_display = ("username", "full_name", "phone_number", "managed_account", "is_approved", "is_staff", "can_use_chatbot", "is_active", "date_joined")
    list_filter = ("is_approved", "is_staff", "is_active", "is_superuser", "can_use_chatbot")
    search_fields = ("username", "phone_number", "full_name")
    actions = [approve_users, unapprove_users, make_staff]

    fieldsets = (
        (None, {"fields": ("username", "phone_number", "password")}),
        ("Personal Info", {"fields": ("full_name",)}),
        ("Delegated Access", {"fields": ("managed_account",)}),
        ("Permissions & Approval", {"fields": ("is_approved", "is_active", "is_staff", "is_superuser", "can_use_chatbot", "groups", "user_permissions")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "phone_number", "full_name", "password1", "password2", "managed_account", "is_approved", "is_staff", "can_use_chatbot", "is_active"),
            },
        ),
    )


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__",)

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
