from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models


class PropertyType(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="property_types")
    name = models.CharField("Type name", max_length=100)
    has_units = models.BooleanField("Has units / apartments", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="unique_property_type_per_owner")]

    def __str__(self):
        return self.name


DEFAULT_PROPERTY_TYPES = [
    ("Home", False),
    ("Apartment", True),
    ("Commercial", False),
    ("Mixed", True),
]


def ensure_default_property_types(owner):
    """Create the starter property types for an owner that has none yet."""
    if owner and not PropertyType.objects.filter(owner=owner).exists():
        PropertyType.objects.bulk_create(
            [PropertyType(owner=owner, name=name, has_units=has_units) for name, has_units in DEFAULT_PROPERTY_TYPES]
        )


class Property(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="properties")
    name = models.CharField("Property name", max_length=150)
    property_type = models.ForeignKey(
        PropertyType, on_delete=models.SET_NULL, null=True, blank=True, related_name="properties"
    )
    location = models.CharField(max_length=200)
    total_rentable_spaces = models.PositiveIntegerField(default=1)
    electricity_account_no = models.CharField("Electricity account no.", max_length=50, blank=True)
    water_account_no = models.CharField("Water account no.", max_length=50, blank=True)
    cover_image = models.ImageField(upload_to="property_covers/", null=True, blank=True)
    description = models.TextField(blank=True)
    is_published = models.BooleanField(
        "Published to Explore",
        default=False,
        help_text="Show this property on the public /explore page. Publishing requires a cover image.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def has_cover_image(self):
        return bool(self.cover_image)

    @property
    def has_units(self):
        if self.property_type_id:
            return self.property_type.has_units
        return self.units.exists()

    # ── Occupancy ────────────────────────────────────────────────────────────

    def active_rental_agreements(self):
        """Active agreements using this property, directly or via a unit/room.

        An agreement may store ``property``, ``unit``, ``room`` or a
        combination of them, so ``rental_agreements`` alone would miss
        unit-only and room-only agreements.
        """
        from rentals.models import RentalAgreement

        return (
            RentalAgreement.objects.filter(status="active")
            .filter(
                models.Q(property=self)
                | models.Q(unit__property=self)
                | models.Q(room__unit__property=self)
            )
            .select_related("tenant", "property", "unit", "room")
        )

    @staticmethod
    def _occupied_unit_ids(units, agreements):
        """Return the ids of units fully covered by active agreements."""
        unit_ids = {unit.pk for unit in units}
        if any(
            agreement.unit_id is None and agreement.room_id is None
            for agreement in agreements
        ):
            # A whole-property agreement covers every unit.
            return unit_ids

        occupied_unit_ids = set()
        rented_room_ids = {a.room_id for a in agreements if a.room_id}
        for agreement in agreements:
            if agreement.room_id is None and agreement.unit_id in unit_ids:
                occupied_unit_ids.add(agreement.unit_id)
        for unit in units:
            if unit.pk in occupied_unit_ids:
                continue
            room_ids = {room.pk for room in unit.rooms.all()}
            if room_ids and room_ids <= rented_room_ids:
                occupied_unit_ids.add(unit.pk)
        return occupied_unit_ids

    def get_occupancy(self, agreements=None):
        """Return how much of this property is currently rented.

        A property with units counts one unit as one rentable space. A unit
        rented room by room only counts as occupied once every room in it is
        rented. A property without units is one single rentable space.
        """
        if agreements is None:
            agreements = self.active_rental_agreements()
        agreements = list(agreements)

        units = list(self.units.prefetch_related("rooms")) if self.has_units else []
        if units:
            total_spaces = len(units)
            rented_spaces = len(self._occupied_unit_ids(units, agreements))
        else:
            total_spaces = 1
            rented_spaces = 1 if agreements else 0

        return {
            "total_spaces": total_spaces,
            "rented_spaces": rented_spaces,
            "occupancy_rate": round(rented_spaces / total_spaces * 100, 1),
            "is_fully_occupied": rented_spaces >= total_spaces,
        }

    def available_units(self):
        """Units that can still be offered in a new rental agreement."""
        if not self.has_units:
            return []
        units = list(self.units.prefetch_related("rooms"))
        agreements = list(self.active_rental_agreements())
        occupied = self._occupied_unit_ids(units, agreements)
        return [unit for unit in units if unit.pk not in occupied]

    @property
    def is_fully_occupied(self):
        return self.get_occupancy()["is_fully_occupied"]


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


class ExploreSettings(models.Model):
    """Contact details shown on the public Explore page.

    This is a singleton: the public Explore page is shared by every owner,
    so there is exactly one set of company contact details.
    """

    whatsapp_number = models.CharField(
        "WhatsApp number",
        max_length=30,
        blank=True,
        help_text="Number opened by the Contact us buttons. Include the country code, e.g. +252 61 234 5678.",
    )
    contact_phone = models.CharField(
        "Contact phone",
        max_length=30,
        blank=True,
        help_text="Used as the WhatsApp fallback when no WhatsApp number is set.",
    )
    contact_email = models.EmailField("Contact email", blank=True)
    contact_address = models.CharField("Office address", max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Explore settings"
        verbose_name_plural = "Explore settings"

    def __str__(self):
        return "Explore settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
