from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models


class PropertyType(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="property_types")
    name = models.CharField("Type name", max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="unique_property_type_per_owner")]

    def __str__(self):
        return self.name


DEFAULT_PROPERTY_TYPES = ["Home", "Apartment", "Commercial", "Mixed"]


def ensure_default_property_types(owner):
    """Create the starter property types for an owner that has none yet."""
    if owner and not PropertyType.objects.filter(owner=owner).exists():
        PropertyType.objects.bulk_create(
            [PropertyType(owner=owner, name=name) for name in DEFAULT_PROPERTY_TYPES]
        )


class Property(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="properties")
    name = models.CharField("Property name", max_length=150)
    property_type = models.ForeignKey(
        PropertyType, on_delete=models.SET_NULL, null=True, blank=True, related_name="properties"
    )
    has_units = models.BooleanField("Has units / apartments", default=False)
    location = models.CharField(max_length=200)
    total_rentable_spaces = models.PositiveIntegerField(default=1)
    electricity_account_no = models.CharField("Electricity account no.", max_length=50, blank=True)
    water_account_no = models.CharField("Water account no.", max_length=50, blank=True)
    cover_image = models.ImageField(upload_to="property_covers/", null=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Unit(models.Model):
    UNIT_TYPES = [("house", "House"), ("apartment", "Apartment"), ("room", "Room"), ("shop", "Shop"), ("office", "Office"), ("other", "Other")]
    RENTAL_MODES = [("whole_unit", "Whole unit"), ("individual_rooms", "Individual rooms")]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="units")
    floor_number = models.PositiveIntegerField(default=1)
    unit_number = models.CharField(max_length=50)
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPES, default="apartment")
    total_rooms = models.PositiveIntegerField(default=1)
    bathrooms = models.PositiveIntegerField(default=1)
    living_rooms = models.PositiveIntegerField(default=1)
    rental_mode = models.CharField(max_length=20, choices=RENTAL_MODES, default="whole_unit")
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["property", "unit_number"], name="unique_unit_per_property")]

    def __str__(self):
        return f"{self.property.name} - {self.unit_number}"


class Room(models.Model):
    ROOM_TYPES = [
        ("living_room", "Living room"),
        ("bedroom", "Bedroom"),
        ("bathroom", "Bathroom"),
        ("kitchen", "Kitchen"),
        ("office", "Office"),
        ("other", "Other room"),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="rooms")
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default="other")
    room_name = models.CharField(max_length=50)
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["unit", "room_name"], name="unique_room_per_unit")]

    def __str__(self):
        return f"{self.unit} - {self.room_name}"


class PropertyAsset(models.Model):
    ASSET_CONDITIONS = [
        ("good", "Good"),
        ("needs_repair", "Needs repair"),
        ("damaged", "Damaged"),
        ("missing", "Missing"),
    ]
    RESPONSIBLE_PARTIES = [
        ("owner", "Owner"),
        ("tenant", "Customer"),
        ("shared", "Shared"),
    ]

    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name="assets"
    )
    name = models.CharField("Item name", max_length=150)
    quantity = models.PositiveIntegerField(default=1)
    condition = models.CharField(
        max_length=20, choices=ASSET_CONDITIONS, default="good"
    )
    responsible_party = models.CharField(
        max_length=20, choices=RESPONSIBLE_PARTIES, default="tenant"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.property.name} - {self.name}"
