from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, username, phone_number, password=None, **extra_fields):
        if not username:
            raise ValueError("Username is required")
        if not phone_number:
            raise ValueError("Phone number is required")
        user = self.model(username=username, phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_approved", True)
        return self.create_user(username, phone_number, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=50, unique=True)
    phone_number = models.CharField(max_length=20, unique=True)
    full_name = models.CharField("Full name", max_length=150)
    managed_account = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_users",
        verbose_name="Managed account",
        help_text="Choose the account whose data this user manages (e.g. Farxaan)."
    )
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField("Approved", default=False)
    is_staff = models.BooleanField(default=False)
    can_use_chatbot = models.BooleanField("AI Chatbot", default=False, help_text="Optional: allow this user to use the AI Chatbot")
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["phone_number", "full_name"]

    def get_data_owner(self):
        """Return the effective owner of data (parent account if delegated, else self)."""
        return self.managed_account if self.managed_account_id else self

    def clean(self):
        """Enforce one-level delegation (Owner <- Manager).

        Prevents self-referencing links and delegation chains such as
        Owner -> Manager A -> Manager B, which would silently change
        Manager B's effective data owner away from the Hirgal Owner.
        """
        super().clean()
        if not self.managed_account_id:
            return
        if self.managed_account_id == self.pk:
            raise ValidationError({"managed_account": "A user cannot be their own managed account."})
        if self.managed_account.managed_account_id:
            raise ValidationError(
                {"managed_account": "A managed user cannot be a managed account. Delegated access must point directly to the owner."}
            )

    def __str__(self):
        return f"{self.full_name} ({self.username})"


class SiteSettings(models.Model):
    gemini_api_key = models.CharField("Gemini API Key", max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
