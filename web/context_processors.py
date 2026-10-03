from django.db.models import Sum
from django.utils import timezone


def language_context(request):
    """Add current language to template context."""
    lang = request.GET.get("lang") or request.session.get("language", "en")
    if lang not in ("en", "so"):
        lang = "en"
    request.session["language"] = lang
    return {"current_language": lang}


def rent_notification(request):
    """Unpaid-rent summary for the topbar notification bell.

    Returns {"rent_notification": {"total": N, "unpaid": [...]}} where each
    unpaid entry has tenant_id, name, due and remaining for this month.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    from finance.models import Payment
    from rentals.models import RentalAgreement

    owner = user.get_data_owner()
    today = timezone.localdate()
    first_day = today.replace(day=1)

    active_rows = list(
        RentalAgreement.objects.filter(tenant__owner=owner, status="active").values(
            "id", "monthly_rent", "tenant_id", "tenant__full_name"
        )
    )
    paid_map = {
        row["rental_agreement_id"]: row["total"]
        for row in Payment.objects.filter(
            rental_agreement__tenant__owner=owner,
            payment_date__gte=first_day,
            payment_date__lte=today,
        )
        .values("rental_agreement_id")
        .annotate(total=Sum("amount"))
    }

    unpaid = []
    for row in active_rows:
        remaining = row["monthly_rent"] - (paid_map.get(row["id"]) or 0)
        if remaining > 0:
            unpaid.append(
                {
                    "tenant_id": row["tenant_id"],
                    "name": row["tenant__full_name"],
                    "due": row["monthly_rent"],
                    "remaining": remaining,
                }
            )

    return {
        "rent_notification": {
            "total": len(active_rows),
            "unpaid": unpaid,
            "month_label": today.strftime("%B %Y"),
        }
    }
