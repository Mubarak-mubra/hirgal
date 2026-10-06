from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User
from properties.models import Property


class AuthenticationApiTests(APITestCase):
    registration_data = {
        "username": "farhan",
        "full_name": "Farhan Xasan",
        "phone_number": "+252612345678",
        "password": "SafePassword123!",
    }

    def test_user_can_register(self):
        response = self.client.post(reverse("register"), self.registration_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("Wait for admin approval", response.data["detail"])
        self.assertFalse(User.objects.get(username="farhan").is_approved)

    def test_user_can_login_with_username_or_phone(self):
        self.client.post(reverse("register"), self.registration_data)
        User.objects.filter(username="farhan").update(is_approved=True)
        for identifier in ("farhan", "+252612345678"):
            response = self.client.post(reverse("login"), {"username_or_phone": identifier, "password": "SafePassword123!"})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("refresh", response.data)

    def test_authenticated_user_can_view_profile(self):
        user = User.objects.create_user(
            username="farhan", phone_number="+252612345678",
            password="SafePassword123!", full_name="Farhan Xasan", is_approved=True,
        )
        login_response = self.client.post(
            reverse("login"),
            {"username_or_phone": "farhan", "password": "SafePassword123!"},
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")
        response = self.client.get(reverse("current-user"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "farhan")

    def test_delegated_account_access_in_web(self):
        farhan = User.objects.create_user(
            username="farhan", phone_number="+252611111111",
            password="Password123!", full_name="Farhan Xasan", is_approved=True,
        )
        liban = User.objects.create_user(
            username="liban", phone_number="+252622222222",
            password="Password123!", full_name="Liban Mohamed", is_approved=True,
            managed_account=farhan
        )

        # Create property for Farhan
        prop = Property.objects.create(owner=farhan, name="Farhan Tower", location="Mogadishu")

        # Liban logs into the web UI
        self.client.login(username="liban", password="Password123!")
        response = self.client.get(reverse("web-properties"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Farhan Tower", response.content.decode())


class ManagedAccountValidationTests(TestCase):
    """One-level delegation invariant: Owner <- Manager, no self or chained links."""

    def make_user(self, username, phone_number, **extra_fields):
        return User.objects.create_user(
            username=username, phone_number=phone_number,
            password="SafePassword123!", full_name=username.title(),
            is_approved=True, **extra_fields,
        )

    def test_owner_without_managed_account_is_valid(self):
        owner = self.make_user("owner_a", "+252615000301")
        owner.full_clean()
        self.assertIsNone(owner.managed_account)
        self.assertEqual(owner.get_data_owner(), owner)

    def test_manager_pointing_to_owner_is_valid(self):
        owner = self.make_user("owner_b", "+252615000302")
        manager = self.make_user("manager_b", "+252615000303", managed_account=owner)
        manager.full_clean()
        self.assertEqual(manager.managed_account, owner)

    def test_user_cannot_point_managed_account_to_itself(self):
        user = self.make_user("selfref", "+252615000304")
        user.managed_account = user
        with self.assertRaises(ValidationError) as cm:
            user.full_clean()
        self.assertIn("managed_account", cm.exception.message_dict)

    def test_manager_cannot_point_to_another_manager(self):
        owner = self.make_user("owner_c", "+252615000305")
        manager_a = self.make_user("manager_c", "+252615000306", managed_account=owner)
        manager_b = self.make_user("manager_d", "+252615000307")
        manager_b.managed_account = manager_a
        with self.assertRaises(ValidationError) as cm:
            manager_b.full_clean()
        self.assertIn("managed_account", cm.exception.message_dict)

    def test_manager_to_owner_behavior_unchanged(self):
        owner = self.make_user("owner_d", "+252615000308")
        manager = self.make_user("manager_e", "+252615000309", managed_account=owner)
        manager.full_clean()
        manager.save()
        manager.refresh_from_db()
        self.assertEqual(manager.managed_account_id, owner.pk)

    def test_get_data_owner_returns_owner_for_manager(self):
        owner = self.make_user("owner_e", "+252615000310")
        manager = self.make_user("manager_f", "+252615000311", managed_account=owner)
        self.assertEqual(manager.get_data_owner(), owner)
