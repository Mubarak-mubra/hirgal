from django.db import migrations, models


def approve_existing_users(apps, schema_editor):
    apps.get_model("accounts", "User").objects.all().update(is_approved=True)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_user_username_alter_user_full_name")]
    operations = [
        migrations.AddField("user", "is_approved", models.BooleanField(default=False, verbose_name="La ansixiyay")),
        migrations.RunPython(approve_existing_users, migrations.RunPython.noop),
    ]
