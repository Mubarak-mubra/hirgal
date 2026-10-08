from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Invoice, InvoiceLine
from .services import post_invoice, cancel_journal_entry_for_object


@receiver(post_save, sender=Invoice)
def invoice_post_save(sender, instance, created, **kwargs):
    post_invoice(instance)


@receiver(post_delete, sender=Invoice)
def invoice_post_delete(sender, instance, **kwargs):
    cancel_journal_entry_for_object(instance)


@receiver(post_save, sender=InvoiceLine)
def invoice_line_post_save(sender, instance, created, **kwargs):
    """Keep the invoice JE in sync when lines change outside the invoice views
    (e.g. Django admin inlines, direct model edits)."""
    if instance.invoice_id:
        post_invoice(instance.invoice)


@receiver(post_delete, sender=InvoiceLine)
def invoice_line_post_delete(sender, instance, **kwargs):
    # Defensive lookup: during a cascade the parent row may already be gone.
    if instance.invoice_id:
        invoice = Invoice.objects.filter(pk=instance.invoice_id).first()
        if invoice:
            post_invoice(invoice)
