from datetime import date
from decimal import ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from . import pickup
from .models import Booking, HandlingUnit, Quote, QuotedUnit, QuoteLineItem, QuoteRequest


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


class ClassPreviewSerializer(serializers.ModelSerializer):
    """Input for `POST /api/class-preview/`: one unit's weight and dimensions (Slice 5).

    The fields come from `HandlingUnit`, so the whole-number rule, the minimum of 1 and the size
    and weight limits are the same ones the quote request enforces, and all four are required.
    """

    class Meta:
        model = HandlingUnit
        fields = ["weight_lb", "length_in", "width_in", "height_in"]


class ClassPreviewResultSerializer(HandlingUnitSerializer):
    """Output for `POST /api/class-preview/`: reuses the density and class fields above, so the
    2-decimal rounding is the existing rule and not a copy."""

    class Meta(HandlingUnitSerializer.Meta):
        fields = ["density", "suggested_class"]
        read_only_fields = fields


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


PRICE_PREVIEW_NOTE = "Estimate only. Your final price is set when you request quotes."


class PricePreviewUnitSerializer(serializers.ModelSerializer):
    """One unit in `POST /api/price-preview/`: only the fields that change the price (Slice 5).

    Built from `HandlingUnit`, so the limits, the whole-number rule and the freight class choices
    are the quote request's own. The class may be left blank; the suggested class prices the unit.
    """

    class Meta:
        model = HandlingUnit
        fields = [
            "quantity",
            "length_in",
            "width_in",
            "height_in",
            "weight_lb",
            "freight_class",
        ]


class PricePreviewSerializer(serializers.ModelSerializer):
    """Input for `POST /api/price-preview/`: the quote request fields that change the price.

    Addresses, the pickup date and the unit details that never change a price are not asked for.
    Built from `QuoteRequest`, so the ZIP check and the location type choices are the same ones
    the quote request enforces.
    """

    handling_units = PricePreviewUnitSerializer(many=True, allow_empty=False)

    class Meta:
        model = QuoteRequest
        fields = [
            "origin_postal_code",
            "origin_location_type",
            "destination_postal_code",
            "destination_location_type",
            "liftgate_requested",
            "appointment_requested",
            "handling_units",
        ]


class PricePreviewPriceSerializer(serializers.Serializer):
    """One carrier's price in the preview response; takes a `services.CarrierPrice`."""

    carrier = serializers.SerializerMethodField()
    total = serializers.DecimalField(max_digits=10, decimal_places=2, source="price.price")
    transit_days = serializers.IntegerField(source="price.transit_days")
    line_items = QuoteLineItemSerializer(many=True, source="price.line_items")

    def get_carrier(self, carrier_price) -> dict:
        return {"code": carrier_price.tariff.code, "name": carrier_price.tariff.name}


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


class BookingSerializer(serializers.ModelSerializer):
    """A stored booking, read-only. `confirmation_total` is the quote's price, read from the quote;
    the bill of lading itself is served by its own endpoint and never shows a price."""

    booking_number = serializers.CharField(read_only=True)
    quote = serializers.IntegerField(source="quote_id", read_only=True)
    carrier = serializers.SerializerMethodField()
    confirmation_total = serializers.DecimalField(
        source="quote.total", max_digits=10, decimal_places=2, read_only=True
    )
    shipper_contact = serializers.SerializerMethodField()
    receiver_contact = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_number",
            "status",
            "quote",
            "carrier",
            "confirmation_total",
            "booked_at",
            "shipper_contact",
            "receiver_contact",
            "special_instructions",
            "cancelled_at",
            "cancel_reason",
        ]
        read_only_fields = fields

    def get_carrier(self, booking: Booking) -> dict:
        return {"code": booking.quote.carrier_code, "name": booking.quote.carrier_name}

    def get_shipper_contact(self, booking: Booking) -> dict:
        return {
            "name": booking.shipper_name,
            "phone": booking.shipper_phone,
            "email": booking.shipper_email,
        }

    def get_receiver_contact(self, booking: Booking) -> dict:
        return {
            "name": booking.receiver_name,
            "phone": booking.receiver_phone,
            "email": booking.receiver_email,
        }
