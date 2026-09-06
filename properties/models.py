from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models


class Property(models.Model):
    PROPERTY_TYPES = [("home", "Guri"), ("apartment", "Apartment"), ("commercial", "Ganacsi"), ("mixed", "Isku-dhafan")]
    RESIDENTIAL_STRUCTURES = [("villa", "Filo"), ("multi_floor", "Guri dabaq")]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="properties")
    name = models.CharField("Magaca hantida", max_length=150)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES, default="home")
    residential_structure = models.CharField(max_length=20, choices=RESIDENTIAL_STRUCTURES, default="villa")
    location = models.CharField(max_length=200)
    total_rentable_spaces = models.PositiveIntegerField(default=1)
    cover_image = models.ImageField(upload_to="property_covers/", null=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Unit(models.Model):
    UNIT_TYPES = [("house", "Guri"), ("apartment", "Apartment"), ("room", "Qol"), ("shop", "Dukaan"), ("office", "Xafiis"), ("other", "Kale")]
    RENTAL_MODES = [("whole_unit", "Guriga oo dhan"), ("individual_rooms", "Qolal gaar-gaar ah")]

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
        ("living_room", "Qolka fadhiga"),
        ("bedroom", "Qolka jiifka"),
        ("bathroom", "Musqusha"),
        ("kitchen", "Jikada"),
        ("office", "Xafiiska"),
        ("other", "Qol kale"),
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
        ("good", "Fiican"),
        ("needs_repair", "Dayactir u baahan"),
        ("damaged", "Waxyeelloobay"),
        ("missing", "Maqan"),
    ]
    RESPONSIBLE_PARTIES = [
        ("owner", "Milkiilaha"),
        ("tenant", "Kiraystaha"),
        ("shared", "Labada dhinac"),
    ]

    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name="assets"
    )
    name = models.CharField("Magaca alaabta", max_length=150)
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
