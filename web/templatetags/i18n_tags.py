import re
from django import template
from django.utils.safestring import mark_safe
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


@register.filter(name="markdown_format")
def markdown_format(text):
    """Convert simple markdown to HTML for AI chat responses."""
    if not text:
        return ""
    s = text
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*\*(.*?)\*\*\*", r"<strong><em>\1</em></strong>", s)
    s = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*(.*?)\*", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r'<code style="background:#e2e8f0;padding:2px 6px;border-radius:4px;font-size:12px;">\1</code>', s)
    s = re.sub(r"^[\*\-] (.+)$", r"<li>\1</li>", s, flags=re.MULTILINE)

    parts = re.split(r"\n+", s)
    result = []
    in_list = False
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        if stripped.startswith("<li>"):
            if not in_list:
                result.append('<ul style="list-style:disc;padding-left:20px;margin:8px 0;">')
                in_list = True
            result.append(stripped)
        else:
            if in_list:
                result.append("</ul>")
                in_list = False
            result.append("<p style='margin:8px 0'>" + stripped + "</p>")
    if in_list:
        result.append("</ul>")
    return mark_safe("".join(result))
