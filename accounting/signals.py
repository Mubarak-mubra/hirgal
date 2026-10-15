from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from .models import Invoice, InvoiceLine
from .services import post_invoice, cancel_journal_entry_for_object, sync_invoice_payment_status


@receiver(post_save, sender=Invoice)
def invoice_post_save(sender, instance, created, **kwargs):
    post_invoice(instance)


@receiver(post_delete, sender=Invoice)
def invoice_post_delete(sender, instance, **kwargs):
    cancel_journal_entry_for_object(instance)


@receiver(pre_delete, sender=InvoiceLine)
def invoice_line_pre_delete(sender, instance, **kwargs):
    """Deleting a line must never zero out or under-collect an invoice that
    already holds payments. Django's Collector runs this before any SQL, so a
    raise here deletes nothing (instance, queryset, and formset paths all go
    through it because this receiver disables the fast-delete shortcut)."""
    if not instance.invoice_id:
        return
    invoice = instance.invoice
    if not invoice.payments.exists():
        return
    total_paid = invoice.payments.aggregate(total=Sum("amount"))["total"] or 0
    remaining = invoice.lines.exclude(pk=instance.pk).aggregate(total=Sum("amount"))["total"] or 0
    if remaining <= 0 or remaining < total_paid:
        raise ValidationError(
            "This invoice has payments: deleting this line would reduce the "
            "invoice total below the amount already collected (or to zero)."
        )


@receiver(post_save, sender=InvoiceLine)
def invoice_line_post_save(sender, instance, created, **kwargs):
    """Keep the invoice JE in sync when lines change outside the invoice views
    (e.g. Django admin inlines, direct model edits)."""
    if instance.invoice_id:
        sync_invoice_payment_status(instance.invoice)
        post_invoice(instance.invoice)


@receiver(post_delete, sender=InvoiceLine)
def invoice_line_post_delete(sender, instance, **kwargs):
    # Defensive lookup: during a cascade the parent row may already be gone.
    if instance.invoice_id:
        invoice = Invoice.objects.filter(pk=instance.invoice_id).first()
        if invoice:
            sync_invoice_payment_status(invoice)
            post_invoice(invoice)
