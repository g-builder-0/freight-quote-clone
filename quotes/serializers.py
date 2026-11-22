from datetime import date
from decimal import ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from . import pickup
from .models import HandlingUnit, Quote, QuotedUnit, QuoteLineItem, QuoteRequest


def get_today() -> date:
    """Today's date in the project time zone (America/Chicago).

    Kept as a small function so API tests can replace it with a fixed date.
    """
    return timezone.localdate()


def get_now():
    """The current time. Kept as a small function so API tests can replace it with a fixed time."""
    return timezone.now()


class HandlingUnitSerializer(serializers.ModelSerializer):
    # Computed on every read from the saved weight and dimensions (never stored). Density goes
    # out as a JSON string rounded to 2 decimals, for example "9.60". It is rounded only for
    # display: the class below is chosen from the unrounded density.
    density = serializers.DecimalField(
        max_digits=12, decimal_places=2, rounding=ROUND_HALF_UP, read_only=True
    )
    suggested_class = serializers.CharField(read_only=True)

    class Meta:
        model = HandlingUnit
        fields = [
            "id",
            "unit_type",
            "quantity",
            "length_in",
            "width_in",
            "height_in",
            "weight_lb",
            "stackable",
            "commodity_description",
            "nmfc_code",
            "freight_class",
            "density",
            "suggested_class",
        ]
        read_only_fields = ["id"]


class QuoteRequestSerializer(serializers.ModelSerializer):
    # allow_empty=False enforces "a quote request must have at least one handling unit".
    handling_units = HandlingUnitSerializer(many=True, allow_empty=False)

    class Meta:
        model = QuoteRequest
        fields = [
            "id",
            "origin_street",
            "origin_city",
            "origin_state",
            "origin_postal_code",
            "origin_location_type",
            "destination_street",
            "destination_city",
            "destination_state",
            "destination_postal_code",
            "destination_location_type",
            "pickup_date",
            "liftgate_requested",
            "appointment_requested",
            "created_at",
            "handling_units",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_pickup_date(self, value: date) -> date:
        try:
            pickup.validate_pickup_date(value, get_today())
        except pickup.PickupDateError as error:
            raise serializers.ValidationError(str(error)) from error
        return value

    @transaction.atomic
    def create(self, validated_data):
        units = validated_data.pop("handling_units")
        quote_request = QuoteRequest.objects.create(**validated_data)
        HandlingUnit.objects.bulk_create(
            [HandlingUnit(quote_request=quote_request, **unit) for unit in units]
        )
        return quote_request


class QuoteLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuoteLineItem
        fields = ["kind", "description", "source", "reason", "amount"]


class QuotedUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotedUnit
        fields = ["handling_unit", "freight_class"]


class QuoteSerializer(serializers.ModelSerializer):
    """A stored quote. Everything except `bookable` and `not_bookable_reason` is read straight from
    the saved row. Those two are computed on every read by `Quote.check_bookable` and never stored:
    they let the front end disable the Book button and say why. The booking endpoint (Slice 3)
    calls the same check and is the real enforcement.
    """

    carrier = serializers.SerializerMethodField()
    line_items = QuoteLineItemSerializer(many=True, read_only=True)
    unit_classes = QuotedUnitSerializer(source="quoted_units", many=True, read_only=True)
    bookable = serializers.SerializerMethodField()
    not_bookable_reason = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            "id",
            "quote_request",
            "carrier",
            "total",
            "line_items",
            "transit_days",
            "estimated_delivery_date",
            "created_at",
            "expires_at",
            "class_table_version",
            "rate_table_version",
            "unit_classes",
            "bookable",
            "not_bookable_reason",
        ]
        read_only_fields = fields

    def get_carrier(self, quote: Quote) -> dict:
        return {"code": quote.carrier_code, "name": quote.carrier_name}

    def _check(self, quote: Quote):
        return quote.check_bookable(get_now())

    def get_bookable(self, quote: Quote) -> bool:
        return self._check(quote).bookable

    def get_not_bookable_reason(self, quote: Quote) -> str:
        return self._check(quote).reason
