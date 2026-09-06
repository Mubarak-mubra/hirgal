from django import template
from web.translations import get_translation, TRANSLATIONS

register = template.Library()


@register.simple_tag(takes_context=True)
def t(context, key):
    """Get translation for a key using the current language."""
    lang = context.get("current_language", "en")
    return get_translation(lang, key)


@register.simple_tag(takes_context=True)
def trans_url(context, url_name, lang=None):
    """Get URL with language parameter."""
    if lang is None:
        current = context.get("current_language", "en")
        lang = "so" if current == "en" else "en"
    return f"?lang={lang}"


@register.simple_tag(takes_context=True)
def other_lang(context):
    """Get the other language code."""
    current = context.get("current_language", "en")
    return "so" if current == "en" else "en"


@register.simple_tag(takes_context=True)
def other_lang_name(context):
    """Get the other language name."""
    current = context.get("current_language", "en")
    return "Soomaali" if current == "en" else "English"


@register.simple_tag(takes_context=True)
def current_lang_name(context):
    """Get the current language name."""
    current = context.get("current_language", "en")
    return "English" if current == "en" else "Soomaali"
