from django.test import TestCase

# Create your tests here.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User


class PropertyApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("farhan", "+252612345678", "SafePassword123!", full_name="Farhan Xasan")
        self.client.force_authenticate(self.user)

    def test_user_can_create_and_list_property(self):
        property_data = {"name": "Sunrise Apartments", "property_type": "apartment", "location": "Hodan"}
        create_response = self.client.post(reverse("property-list"), property_data)
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        list_response = self.client.get(reverse("property-list"))
        self.assertEqual(list_response.data[0]["name"], "Sunrise Apartments")

    def test_user_can_add_unit_to_owned_property(self):
        property_response = self.client.post(reverse("property-list"), {"name": "Sunrise", "location": "Hodan"})
        property_id = property_response.data["id"]
        response = self.client.post(reverse("unit-list", kwargs={"property_id": property_id}), {"unit_number": "102", "unit_type": "apartment", "default_monthly_rent": "500.00"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["property_name"], "Sunrise")

    def test_user_cannot_see_another_users_property(self):
        other_user = User.objects.create_user("owner2", "+252612345679", "SafePassword123!", full_name="Owner Two")
        self.client.force_authenticate(other_user)
        self.client.post(reverse("property-list"), {"name": "Other Property", "location": "Hodan"})
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("property-list"))
        self.assertEqual(response.data, [])
