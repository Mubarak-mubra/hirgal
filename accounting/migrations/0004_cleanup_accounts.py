from django.db import migrations, models


def delete_misconfigured_accounts(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')
    Account.objects.filter(code='1000').delete()


def mark_system_accounts(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')
    SYSTEM_CODES = ['1010', '1200', '2010', '2050', '3010', '3020', '4010', '5010']
    Account.objects.filter(code__in=SYSTEM_CODES).update(is_system=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0003_account_bank_account_alter_account_category_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='is_system',
            field=models.BooleanField(default=False, help_text='Haddii ay tahay system, ma tirtiri karto', verbose_name='Xisaabta System'),
        ),
        migrations.RunPython(delete_misconfigured_accounts, migrations.RunPython.noop),
        migrations.RunPython(mark_system_accounts, migrations.RunPython.noop),
    ]
