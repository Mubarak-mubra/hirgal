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
        self.assertIn("Sug ansixinta", response.data["detail"])
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
