from calendar import monthrange
from django.db.models import Count, Q
from django.utils import timezone


def language_context(request):
    """Add current language to template context."""
    lang = request.GET.get("lang") or request.session.get("language", "en")
    if lang not in ("en", "so"):
        lang = "en"
    request.session["language"] = lang
    return {"current_language": lang}


def rent_notification(request):
    """Expose a current-month rent invoice reminder to the topbar bell."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    from accounting.models import Invoice
    from rentals.models import RentalAgreement

    owner = user.get_data_owner()
    today = timezone.localdate()
    first_day = today.replace(day=1)
    last_day = first_day.replace(
        day=monthrange(first_day.year, first_day.month)[1]
    )

    eligible_agreements = RentalAgreement.objects.filter(
        tenant__owner=owner,
        status__in=("active", "ended"),
        start_date__lte=first_day,
        monthly_rent__gt=0,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=last_day))

    monthly_drafts = Invoice.objects.filter(
        owner=owner,
        status__in=("draft", "sent", "paid"),
        rental_agreement__isnull=False,
    ).filter(
        Q(billing_period=first_day)
        | (
            Q(billing_period__isnull=True)
            & Q(rental_agreement__isnull=False)
            & (
                Q(date__year=today.year, date__month=today.month)
                | Q(due_date__year=today.year, due_date__month=today.month)
            )
        )
    )
    status_counts = {
        row["status"]: row["count"]
        for row in monthly_drafts.values("status").annotate(count=Count("pk"))
    }
    draft_count = status_counts.get("draft", 0)
    sent_count = status_counts.get("sent", 0)
    paid_count = status_counts.get("paid", 0)
    invoice_count = draft_count + sent_count + paid_count
    needs_generation = invoice_count == 0 and eligible_agreements.exists()

    return {
        "rent_notification": {
            "draft_count": draft_count,
            "sent_count": sent_count,
            "paid_count": paid_count,
            "invoice_count": invoice_count,
            "needs_generation": needs_generation,
            "should_show": invoice_count > 0 or needs_generation,
            "month_label": today.strftime("%B %Y"),
            "month_param": today.strftime("%Y-%m"),
        }
    }
