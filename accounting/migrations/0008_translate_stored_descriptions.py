from django.db import migrations

ACCOUNT_DESCRIPTIONS = {
    "Lacagta gacanta ku jirta": "Petty cash and physical cash",
    "Bangiga iyo Mobile Money": "Bank accounts and mobile money wallets",
    "Lacagta aan kireystayaasha ku leenahay": "Money customers owe us",
    "Lacagaha cid kale lagu leeyahay": "Money we owe to others",
    "Deposits-ka kiraystayaasha": "Tenant security deposits",
    "Raasamaalka milkiilaha": "Owner's capital investment",
    "Faa'iidada la soo uruuriyay": "Accumulated net income",
    "Kirada ka timid guryaha": "Income from rental properties",
    "Dakhliga kale": "Late fees and other income",
    "Dayactirka iyo hagaajinta": "Property maintenance costs",
    "Biilka biyaha iyo korontada": "Water, electricity, internet bills",
    "Kharashyada guud": "Office and admin expenses",
}

DESCRIPTION_PREFIXES = [
    ("Lacag kirada - ", "Rent payment - "),
    ("Lacag ka timid ", "Payment from "),
    ("Kharash - ", "Expense - "),
    ("Dayactir - ", "Repair - "),
    ("Biil - ", "Invoice - "),
    ("Bangiga auto-created: ", "Auto-created bank: "),
]


def translate_stored_text(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    for old, new in ACCOUNT_DESCRIPTIONS.items():
        Account.objects.filter(description=old).update(description=new)
    for old, new in DESCRIPTION_PREFIXES:
        for obj in Account.objects.filter(description__startswith=old):
            obj.description = new + obj.description[len(old):]
            obj.save(update_fields=["description"])

    for model_name in ("JournalEntry", "JournalEntryLine"):
        Model = apps.get_model("accounting", model_name)
        for old, new in DESCRIPTION_PREFIXES:
            for obj in Model.objects.filter(description__startswith=old):
                obj.description = new + obj.description[len(old):]
                obj.save(update_fields=["description"])
        for obj in Model.objects.filter(description="Dayactir"):
            obj.description = "Repair"
            obj.save(update_fields=["description"])

    GeneralExpense = apps.get_model("finance", "GeneralExpense")
    GeneralExpense.objects.filter(title="Dayactir").update(title="Repair")


def untranslate_stored_text(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    for old, new in ACCOUNT_DESCRIPTIONS.items():
        Account.objects.filter(description=new).update(description=old)
    for old, new in DESCRIPTION_PREFIXES:
        for obj in Account.objects.filter(description__startswith=new):
            obj.description = old + obj.description[len(new):]
            obj.save(update_fields=["description"])

    for model_name in ("JournalEntry", "JournalEntryLine"):
        Model = apps.get_model("accounting", model_name)
        for old, new in DESCRIPTION_PREFIXES:
            for obj in Model.objects.filter(description__startswith=new):
                obj.description = old + obj.description[len(new):]
                obj.save(update_fields=["description"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0007_alter_account_bank_account_alter_account_category_and_more"),
        ("finance", "0009_alter_bankaccount_account_name_and_more"),
    ]

    operations = [
        migrations.RunPython(translate_stored_text, untranslate_stored_text),
    ]
