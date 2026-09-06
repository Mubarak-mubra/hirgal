from django.core.management.base import BaseCommand
from finance.models import GeneralExpense, MaintenanceRepair


class Command(BaseCommand):
    help = "Set payment_status to 'paid' for existing records that have a bank_account set"

    def handle(self, *args, **options):
        expenses = GeneralExpense.objects.filter(bank_account__isnull=False, payment_status="unpaid")
        for e in expenses:
            e.payment_status = "paid"
            e.save(update_fields=["payment_status"])

        repairs = MaintenanceRepair.objects.filter(bank_account__isnull=False, payment_status="unpaid")
        for r in repairs:
            r.payment_status = "paid"
            r.save(update_fields=["payment_status"])

        self.stdout.write(self.style.SUCCESS(
            "Fixed %d expenses and %d repairs" % (expenses.count(), repairs.count())
        ))
