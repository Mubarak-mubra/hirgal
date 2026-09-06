from django.urls import path

from .views import (
    PropertyAssetDetailView,
    PropertyAssetListCreateView,
    PropertyDetailView,
    PropertyListCreateView,
    RoomDetailView,
    RoomListCreateView,
    UnitDetailView,
    UnitListCreateView,
)

urlpatterns = [
    path("", PropertyListCreateView.as_view(), name="property-list"),
    path("<int:pk>/", PropertyDetailView.as_view(), name="property-detail"),
    path("<int:property_id>/units/", UnitListCreateView.as_view(), name="unit-list"),
    path("units/<int:pk>/", UnitDetailView.as_view(), name="unit-detail"),
    path("units/<int:unit_id>/rooms/", RoomListCreateView.as_view(), name="room-list"),
    path("rooms/<int:pk>/", RoomDetailView.as_view(), name="room-detail"),
    path("assets/", PropertyAssetListCreateView.as_view(), name="property-asset-list"),
    path("assets/<int:pk>/", PropertyAssetDetailView.as_view(), name="property-asset-detail"),
]
