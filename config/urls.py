"""
URL configuration for config project.
"""

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

admin.site.site_header = "Hirgal Kiro Administration"
admin.site.site_title = "Hirgal Kiro"
admin.site.index_title = "Manage data"

urlpatterns = [
    path("", include("web.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
