"""
URL configuration for config project.
"""

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

admin.site.site_header = "Maamulka Hirgal Kiro"
admin.site.site_title = "Hirgal Kiro"
admin.site.index_title = "Maamulka xogta"

urlpatterns = [
    path("", include("web.urls")),
    path("api/v1/properties/", include("properties.urls")),
    path("api/v1/rentals/", include("rentals.urls")),
    path("api/v1/finance/", include("finance.urls")),
    path("api/v1/accounts/", include("accounts.urls")),
    path("api/v1/accounting/", include("accounting.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
