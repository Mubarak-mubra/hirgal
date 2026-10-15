from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounting.services import generate_monthly_rent_invoices


class Command(BaseCommand):
    help = "Create draft rent invoices for agreements covering a month. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--month",
            help="Billing month in YYYY-MM format (defaults to the current month).",
        )

    def handle(self, *args, **options):
        month = options.get("month")
        if month:
            try:
                period = datetime.strptime(month, "%Y-%m").date()
            except ValueError as exc:
                raise CommandError("--month must use YYYY-MM format, for example 2026-10.") from exc
        else:
            period = timezone.localdate()

        result = generate_monthly_rent_invoices(period)
        self.stdout.write(
            self.style.SUCCESS(
                f"{result['period']:%B %Y}: created {len(result['created'])} draft invoice(s); "
                f"skipped {result['skipped']} agreement(s) with an existing invoice."
            )
        )
