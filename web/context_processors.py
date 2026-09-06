def language_context(request):
    """Add current language to template context."""
    lang = request.GET.get("lang") or request.session.get("language", "en")
    if lang not in ("en", "so"):
        lang = "en"
    request.session["language"] = lang
    return {"current_language": lang}
