from django.test import TestCase

# Create your tests here.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


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
        self.assertIn("access", response.data)

    def test_user_can_login_with_username_or_phone(self):
        self.client.post(reverse("register"), self.registration_data)
        for identifier in ("farhan", "+252612345678"):
            response = self.client.post(reverse("login"), {"username_or_phone": identifier, "password": "SafePassword123!"})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("refresh", response.data)

    def test_authenticated_user_can_view_profile(self):
        registration_response = self.client.post(reverse("register"), self.registration_data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {registration_response.data['access']}")
        response = self.client.get(reverse("current-user"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "farhan")
