from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Invoice
from .services import post_invoice, cancel_journal_entry_for_object


@receiver(post_save, sender=Invoice)
def invoice_post_save(sender, instance, created, **kwargs):
    post_invoice(instance)


@receiver(post_delete, sender=Invoice)
def invoice_post_delete(sender, instance, **kwargs):
    cancel_journal_entry_for_object(instance)
