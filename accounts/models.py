from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, username, phone_number, password=None, **extra_fields):
        if not username:
            raise ValueError("Magaca isticmaalaha waa loo baahan yahay")
        if not phone_number:
            raise ValueError("Lambarka telefoonka waa loo baahan yahay")
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
    full_name = models.CharField("Magaca oo buuxa", max_length=150)
    managed_account = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_users",
        verbose_name="Sii gelitaanka akoonka (Managed Account)",
        help_text="Dooro akoonka uu isticmaalahani maamulayo xogtiisa (Tusaale: Farxaan)."
    )
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField("La ansixiyay", default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["phone_number", "full_name"]

    def get_data_owner(self):
        """Return the effective owner of data (parent account if delegated, else self)."""
        return self.managed_account if self.managed_account_id else self

    def __str__(self):
        return f"{self.full_name} ({self.username})"
