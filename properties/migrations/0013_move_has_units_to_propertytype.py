from django.db import migrations, models

UNITS_BY_NAME = {"apartment", "apartments", "mixed", "building"}


def move_has_units_to_type(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    PropertyType = apps.get_model("properties", "PropertyType")
    Property = apps.get_model("properties", "Property")

    for ptype in PropertyType.objects.using(db_alias).all():
        if ptype.properties.exists():
            ptype.has_units = ptype.properties.filter(has_units=True).exists()
        else:
            # No properties yet: infer from the type name
            ptype.has_units = ptype.name.lower() in UNITS_BY_NAME
        ptype.save(update_fields=["has_units"], using=db_alias)


def restore_property_has_units(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Property = apps.get_model("properties", "Property")
    for prop in Property.objects.using(db_alias).all():
        prop.has_units = bool(prop.property_type_id and prop.property_type.has_units)
        prop.save(update_fields=["has_units"], using=db_alias)


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0012_propertytype_has_units"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertytype",
            name="has_units",
            field=models.BooleanField(default=False, verbose_name="Has units / apartments"),
        ),
        migrations.RunPython(move_has_units_to_type, restore_property_has_units),
        migrations.RemoveField(
            model_name="property",
            name="has_units",
        ),
    ]
