from django.db import migrations


def fix_account_descriptions(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')

    # Fix Accounts Receivable (1200) descriptions
    Account.objects.filter(code='1200').update(
        description='Money customers owe us'
    )

    # Fix Accounts Payable (2010) descriptions
    Account.objects.filter(code='2010').update(
        description='Money we owe to others'
    )

    # Fix mismatched bank account descriptions
    Account.objects.filter(code='1021').update(
        description='Auto-created bank: Dahabshiil Bank'
    )
    Account.objects.filter(code='1022').update(
        description='Auto-created bank: EVC-PLUS'
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0004_cleanup_accounts"),
    ]

    operations = [
        migrations.RunPython(fix_account_descriptions, migrations.RunPython.noop),
    ]
