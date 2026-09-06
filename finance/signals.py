from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Payment, GeneralExpense, MaintenanceRepair, BankAccount
from accounting.services import post_payment, post_expense, post_repair, cancel_journal_entry_for_object


@receiver(post_save, sender=BankAccount)
def bank_account_post_save(sender, instance, **kwargs):
    if instance.linked_account:
        new_name = "%s (%s)" % (instance.bank_name, instance.account_number)
        if instance.linked_account.name != new_name:
            instance.linked_account.name = new_name
            instance.linked_account.save(update_fields=["name"])


@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    post_payment(instance)


@receiver(post_delete, sender=Payment)
def payment_post_delete(sender, instance, **kwargs):
    cancel_journal_entry_for_object(instance)


@receiver(post_save, sender=GeneralExpense)
def general_expense_post_save(sender, instance, created, **kwargs):
    post_expense(instance)


@receiver(post_delete, sender=GeneralExpense)
def general_expense_post_delete(sender, instance, **kwargs):
    cancel_journal_entry_for_object(instance)


@receiver(post_save, sender=MaintenanceRepair)
def maintenance_repair_post_save(sender, instance, created, **kwargs):
    post_repair(instance)


@receiver(post_delete, sender=MaintenanceRepair)
def maintenance_repair_post_delete(sender, instance, **kwargs):
    cancel_journal_entry_for_object(instance)
