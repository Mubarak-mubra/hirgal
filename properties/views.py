from django.db.models import Count, Q, Sum
from rest_framework import generics

from .models import Property, PropertyAsset, Room, Unit
from .serializers import PropertyAssetSerializer, PropertySerializer, RoomSerializer, UnitSerializer


class PropertyListCreateView(generics.ListCreateAPIView):
    serializer_class = PropertySerializer

    def get_queryset(self):
        return Property.objects.filter(owner=self.request.user).annotate(
            total_units=Count("units", distinct=True),
            rented_units=Count("units", filter=Q(units__rental_agreements__status="active"), distinct=True),
            expected_monthly_rent=Sum("units__monthly_rent"),
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class PropertyDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertySerializer

    def get_queryset(self):
        return Property.objects.filter(owner=self.request.user).annotate(
            total_units=Count("units", distinct=True),
            rented_units=Count("units", filter=Q(units__rental_agreements__status="active"), distinct=True),
            expected_monthly_rent=Sum("units__monthly_rent"),
        )


class UnitListCreateView(generics.ListCreateAPIView):
    serializer_class = UnitSerializer

    def get_property(self):
        return Property.objects.get(id=self.kwargs["property_id"], owner=self.request.user)

    def get_queryset(self):
        return Unit.objects.filter(property=self.get_property())

    def perform_create(self, serializer):
        serializer.save(property=self.get_property())


class UnitDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UnitSerializer

    def get_queryset(self):
        return Unit.objects.filter(property__owner=self.request.user)


class RoomListCreateView(generics.ListCreateAPIView):
    serializer_class = RoomSerializer

    def get_unit(self):
        return Unit.objects.get(id=self.kwargs["unit_id"], property__owner=self.request.user)

    def get_queryset(self):
        return Room.objects.filter(unit=self.get_unit())

    def perform_create(self, serializer):
        serializer.save(unit=self.get_unit())


class RoomDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoomSerializer

    def get_queryset(self):
        return Room.objects.filter(unit__property__owner=self.request.user)


class PropertyAssetListCreateView(generics.ListCreateAPIView):
    serializer_class = PropertyAssetSerializer

    def get_queryset(self):
        return PropertyAsset.objects.filter(property__owner=self.request.user)

    def perform_create(self, serializer):
        property_instance = Property.objects.get(
            id=self.request.data.get("property_id"), owner=self.request.user
        )
        serializer.save(property=property_instance)


class PropertyAssetDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertyAssetSerializer

    def get_queryset(self):
        return PropertyAsset.objects.filter(property__owner=self.request.user)
