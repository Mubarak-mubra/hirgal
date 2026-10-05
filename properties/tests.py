from django.test import TestCase

# Create your tests here.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from properties.models import Property, PropertyType


class PropertyApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("farhan", "+252612345678", "SafePassword123!", full_name="Farhan Xasan")
        self.client.force_authenticate(self.user)
        self.apartment_type = PropertyType.objects.create(owner=self.user, name="Apartment")

    def test_user_can_create_and_list_property(self):
        property_data = {"name": "Sunrise Apartments", "property_type": self.apartment_type.pk, "location": "Hodan"}
        create_response = self.client.post(reverse("property-list"), property_data)
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        list_response = self.client.get(reverse("property-list"))
        self.assertEqual(list_response.data[0]["name"], "Sunrise Apartments")

    def test_user_can_add_unit_to_owned_property(self):
        property_response = self.client.post(reverse("property-list"), {"name": "Sunrise", "location": "Hodan"})
        property_id = property_response.data["id"]
        response = self.client.post(reverse("unit-list", kwargs={"property_id": property_id}), {"unit_number": "102", "unit_type": "apartment", "monthly_rent": "500.00"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["property_name"], "Sunrise")

    def test_user_cannot_see_another_users_property(self):
        other_user = User.objects.create_user("owner2", "+252612345679", "SafePassword123!", full_name="Owner Two")
        self.client.force_authenticate(other_user)
        self.client.post(reverse("property-list"), {"name": "Other Property", "location": "Hodan"})
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("property-list"))
        self.assertEqual(response.data, [])


class PropertyApiOwnershipTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner_a", "+252615000001", "SafePassword123!", full_name="Owner A")
        self.manager = User.objects.create_user("manager_b", "+252615000002", "SafePassword123!", full_name="Manager B")
        self.manager.managed_account = self.owner
        self.manager.save()
        self.outsider = User.objects.create_user("owner_c", "+252615000003", "SafePassword123!", full_name="Owner C")
        self.property = Property.objects.create(owner=self.owner, name="Owner A Block", location="Hodan")
        self.outsider_property = Property.objects.create(owner=self.outsider, name="Owner C Block", location="Hodan")

    def test_root_owner_creates_and_lists_own_property(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse("property-list"), {"name": "New Block", "location": "Hodan"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Property.objects.get(pk=response.data["id"]).owner, self.owner)
        list_response = self.client.get(reverse("property-list"))
        names = [p["name"] for p in list_response.data]
        self.assertIn("New Block", names)
        self.assertEqual(len(names), 2)

    def test_manager_reads_owner_boundary(self):
        self.client.force_authenticate(self.manager)
        list_response = self.client.get(reverse("property-list"))
        self.assertEqual([p["name"] for p in list_response.data], ["Owner A Block"])
        detail_response = self.client.get(reverse("property-detail", kwargs={"pk": self.property.pk}))
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["name"], "Owner A Block")

    def test_manager_creates_property_under_owner_boundary(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("property-list"), {"name": "Manager Block", "location": "Hodan"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Property.objects.get(pk=response.data["id"])
        self.assertEqual(created.owner, self.owner)
        self.assertNotEqual(created.owner, self.manager)

    def test_unrelated_user_cannot_access_other_boundaries(self):
        self.client.force_authenticate(self.outsider)
        list_response = self.client.get(reverse("property-list"))
        self.assertEqual([p["name"] for p in list_response.data], ["Owner C Block"])
        detail_response = self.client.get(reverse("property-detail", kwargs={"pk": self.property.pk}))
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
