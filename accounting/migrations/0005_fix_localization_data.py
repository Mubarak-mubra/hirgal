from django.db import migrations


def fix_account_descriptions(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')

    # Fix Accounts Receivable (1200) descriptions
    Account.objects.filter(code='1200').update(
        description='Lacagta aan kireystayaasha ku leenahay'
    )

    # Fix Accounts Payable (2010) descriptions
    Account.objects.filter(code='2010').update(
        description='Lacagaha cid kale lagu leeyahay'
    )

    # Fix mismatched bank account descriptions
    Account.objects.filter(code='1021').update(
        description='Bangiga auto-created: Dahabshiil Bank'
    )
    Account.objects.filter(code='1022').update(
        description='Bangiga auto-created: EVC-PLUS'
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0004_cleanup_accounts"),
    ]

    operations = [
        migrations.RunPython(fix_account_descriptions, migrations.RunPython.noop),
    ]
