from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

LEGACY_TYPE_NAMES = {
    "home": "Home",
    "apartment": "Apartment",
    "commercial": "Commercial",
    "mixed": "Mixed",
}


def backfill_property_types(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Property = apps.get_model("properties", "Property")
    PropertyType = apps.get_model("properties", "PropertyType")
    for prop in Property.objects.using(db_alias).all().order_by("pk"):
        legacy = prop.property_type or "home"
        name = LEGACY_TYPE_NAMES.get(legacy, legacy.replace("_", " ").title())
        ptype, _ = PropertyType.objects.using(db_alias).get_or_create(owner_id=prop.owner_id, name=name)
        prop.property_type_new = ptype
        prop.has_units = prop.units.exists() and legacy != "home"
        prop.save(update_fields=["property_type_new", "has_units"], using=db_alias)


def unbackfill_property_types(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Property = apps.get_model("properties", "Property")
    Property.objects.using(db_alias).update(property_type_new=None, has_units=False)


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0011_alter_property_name_alter_property_property_type_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PropertyType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("name", models.CharField(max_length=100, verbose_name="Type name")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="property_types", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["name"],
                "constraints": [models.UniqueConstraint(fields=("owner", "name"), name="unique_property_type_per_owner")],
            },
        ),
        migrations.AddField(
            model_name="property",
            name="has_units",
            field=models.BooleanField(default=False, verbose_name="Has units / apartments"),
        ),
        migrations.AddField(
            model_name="property",
            name="property_type_new",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="properties", to="properties.propertytype"),
        ),
        migrations.RunPython(backfill_property_types, unbackfill_property_types),
        migrations.RemoveField(
            model_name="property",
            name="property_type",
        ),
        migrations.RenameField(
            model_name="property",
            old_name="property_type_new",
            new_name="property_type",
        ),
        migrations.RemoveField(
            model_name="property",
            name="residential_structure",
        ),
    ]
