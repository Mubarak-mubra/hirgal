from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from .models import Payment, GeneralExpense, MaintenanceRepair, BankAccount
from accounting.services import (
    post_payment, post_expense, post_repair, cancel_journal_entry_for_object,
    sync_invoice_payment_status,
)


@receiver(post_save, sender=BankAccount)
def bank_account_post_save(sender, instance, **kwargs):
    if instance.linked_account:
        new_name = "%s (%s)" % (instance.bank_name, instance.account_number)
        if instance.linked_account.name != new_name:
            instance.linked_account.name = new_name
            instance.linked_account.save(update_fields=["name"])


@receiver(pre_save, sender=Payment)
def payment_pre_save(sender, instance, **kwargs):
    if instance.pk:
        instance._previous_invoice_id = sender.objects.filter(pk=instance.pk).values_list("invoice_id", flat=True).first()
    else:
        instance._previous_invoice_id = None


@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    previous_invoice_id = getattr(instance, "_previous_invoice_id", None)
    post_payment(instance)
    if previous_invoice_id and previous_invoice_id != instance.invoice_id:
        invoice_model = sender._meta.get_field("invoice").remote_field.model
        old_invoice = invoice_model.objects.filter(pk=previous_invoice_id).first()
        if old_invoice:
            sync_invoice_payment_status(old_invoice)


@receiver(post_delete, sender=Payment)
def payment_post_delete(sender, instance, **kwargs):
    cancel_journal_entry_for_object(instance)
    if instance.invoice_id:
        sync_invoice_payment_status(instance.invoice)


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
