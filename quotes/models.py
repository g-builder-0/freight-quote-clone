from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from . import pickup, pricing
from .freight_class import (
    CLASS_TABLE_VERSION,
    STANDARD_NMFC_CLASSES,
    calculate_density,
    format_class,
    suggest_class,
)
from .validators import validate_nmfc_code, validate_postal_code, validate_us_state

# Hard limits per handling unit (Slice 1 spec). Carriers set their own limits; these are a
# rough synthesis and are enforced by validation. Dimensions are whole inches, weight whole pounds.
MAX_LENGTH_IN = 144
MAX_WIDTH_IN = 96
MAX_HEIGHT_IN = 96
MAX_WEIGHT_LB = 4000


class LocationType(models.TextChoices):
    BUSINESS_DOCK = "business_dock", "Business with dock"
    RESIDENTIAL = "residential", "Residential"
    LIMITED_ACCESS = "limited_access", "Limited access"
    CONSTRUCTION_SITE = "construction_site", "Construction site"


class UnitType(models.TextChoices):
    PALLET = "pallet", "Pallet"
    CRATE = "crate", "Crate"
    DRUM = "drum", "Drum"
    CARTON = "carton", "Carton"


class QuoteRequest(models.Model):
    """A shipper's request to move freight from an origin to a destination.

    Addresses are flat fields (no separate Address model): each request keeps its own copy of
    the values, so history cannot change later. The state and ZIP rules are shared validators.
    """

    origin_street = models.CharField(max_length=200)
    origin_city = models.CharField(max_length=100)
    origin_state = models.CharField(max_length=2, validators=[validate_us_state])
    origin_postal_code = models.CharField(max_length=10, validators=[validate_postal_code])
    origin_location_type = models.CharField(max_length=20, choices=LocationType.choices)

    destination_street = models.CharField(max_length=200)
    destination_city = models.CharField(max_length=100)
    destination_state = models.CharField(max_length=2, validators=[validate_us_state])
    destination_postal_code = models.CharField(max_length=10, validators=[validate_postal_code])
    destination_location_type = models.CharField(max_length=20, choices=LocationType.choices)

    pickup_date = models.DateField()
    # Requested accessorials (Slice 2). Yes/no flags; existing requests default to no.
    liftgate_requested = models.BooleanField(default=False)
    appointment_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Quote request {self.pk}: {self.origin_city} to {self.destination_city}"


class HandlingUnit(models.Model):
    """One loaded physical piece (pallet, crate, drum or carton) in a quote request.

    Weight and dimensions are for ONE unit. Density and the suggested class are NOT stored:
    they are computed each time from the saved weight and dimensions using the current class
    table (a Slice 2 quote will snapshot them).
    """

    quote_request = models.ForeignKey(
        QuoteRequest, on_delete=models.CASCADE, related_name="handling_units"
    )
    unit_type = models.CharField(max_length=10, choices=UnitType.choices)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    length_in = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_LENGTH_IN)]
    )
    width_in = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_WIDTH_IN)]
    )
    height_in = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_HEIGHT_IN)]
    )
    weight_lb = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_WEIGHT_LB)]
    )
    stackable = models.BooleanField(default=False)
    commodity_description = models.CharField(max_length=200)
    # Optional. Format check only (see validators.py).
    nmfc_code = models.CharField(max_length=10, blank=True, validators=[validate_nmfc_code])
    # Optional class supplied by the shipper. Stored as given, never overwritten by the suggestion.
    freight_class = models.CharField(
        max_length=5,
        blank=True,
        choices=[(freight_class, freight_class) for freight_class in STANDARD_NMFC_CLASSES],
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.get_unit_type_display()} x{self.quantity}: {self.commodity_description}"

    @property
    def density(self) -> Decimal:
        """Density in lb per cubic foot for one unit, exact and unrounded."""
        return calculate_density(self.weight_lb, self.length_in, self.width_in, self.height_in)

    @property
    def suggested_class(self) -> str:
        """Class suggested from the unrounded density, as plain text such as "55" or "92.5"."""
        return format_class(suggest_class(self.density))


# ---------------------------------------------------------------------------------------------
# Slice 2: tariffs (versioned, immutable) and quotes (immutable).
# ---------------------------------------------------------------------------------------------

# A quote is valid for 7 calendar days from its creation time (decisions.md, 2026-11-13).
QUOTE_VALIDITY = timedelta(days=7)


class ImmutableRecordError(Exception):
    """A saved tariff or quote row was changed or deleted."""


class ImmutableModel(models.Model):
    """A row that can be created but never changed or deleted afterwards.

    This is a guard against a bug in a view or service editing history: `save()` on an existing
    row and `delete()` both raise. It does not stop raw queryset updates or SQL, so it is a safety
    net and not a security boundary. Creating child rows for a saved parent is fine.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableRecordError(f"{type(self).__name__} rows cannot be changed once saved.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError(f"{type(self).__name__} rows cannot be deleted.")


class TariffVersion(ImmutableModel):
    """One version of the whole rate table, for example "RATES-2026-1".

    The current version is the one with the latest `created_at` (the id breaks ties). There is no
    flag and no draft state: a version is created complete, in one transaction, and is live at once.
    A rate change creates a NEW version by copying every row (the create_tariff_version command).
    """

    label = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.label

    @classmethod
    def current(cls) -> "TariffVersion | None":
        return cls.objects.order_by("-created_at", "-id").first()


class FeeType(models.TextChoices):
    RESIDENTIAL = pricing.RESIDENTIAL, "Residential"
    LIMITED_ACCESS = pricing.LIMITED_ACCESS, "Limited access"
    LIFTGATE = pricing.LIFTGATE, "Liftgate"
    APPOINTMENT = pricing.APPOINTMENT, "Appointment"


class CarrierTariff(ImmutableModel):
    """One simulated carrier's tariff inside one tariff version. All numbers are illustrative."""

    version = models.ForeignKey(TariffVersion, on_delete=models.PROTECT, related_name="carriers")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=60)
    minimum_charge = models.DecimalField(max_digits=8, decimal_places=2)
    # A fraction: 0.3200 is a 32% fuel surcharge.
    fuel_percent = models.DecimalField(max_digits=5, decimal_places=4)
    transit_adjustment_days = models.SmallIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["version", "code"], name="unique_carrier_per_version")
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.version.label})"

    def to_data(self) -> pricing.CarrierTariffData:
        """The plain-data form the pricing rules use."""
        return pricing.CarrierTariffData(
            code=self.code,
            name=self.name,
            minimum_charge=self.minimum_charge,
            fuel_percent=self.fuel_percent,
            transit_adjustment_days=self.transit_adjustment_days,
            weight_breaks=tuple(
                pricing.WeightBreak(rate.from_lb, rate.to_lb, rate.rate_per_cwt)
                for rate in self.weight_breaks.order_by("from_lb")
            ),
            fees={fee.fee_type: fee.amount for fee in self.fees.all()},
        )


class WeightBreakRate(ImmutableModel):
    """Rate per cwt (at class 100) for a weight tier; `to_lb` is empty for "and up"."""

    carrier_tariff = models.ForeignKey(
        CarrierTariff, on_delete=models.PROTECT, related_name="weight_breaks"
    )
    from_lb = models.PositiveIntegerField()
    to_lb = models.PositiveIntegerField(null=True, blank=True)
    rate_per_cwt = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        ordering = ["carrier_tariff_id", "from_lb"]
        constraints = [
            models.UniqueConstraint(
                fields=["carrier_tariff", "from_lb"], name="unique_weight_break_per_carrier"
            )
        ]

    def __str__(self) -> str:
        upper = "and up" if self.to_lb is None else f"to {self.to_lb}"
        return f"{self.from_lb} {upper} lb: ${self.rate_per_cwt}/cwt"


class AccessorialFee(ImmutableModel):
    carrier_tariff = models.ForeignKey(CarrierTariff, on_delete=models.PROTECT, related_name="fees")
    fee_type = models.CharField(max_length=20, choices=FeeType.choices)
    amount = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        ordering = ["carrier_tariff_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["carrier_tariff", "fee_type"], name="unique_fee_per_carrier"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_fee_type_display()}: ${self.amount}"


@dataclass(frozen=True)
class BookableCheck:
    """Result of Quote.check_bookable: whether the quote can be booked, and if not, why."""

    bookable: bool
    reason: str = ""


class Quote(ImmutableModel):
    """One carrier's price for one quote request, with everything needed to explain it.

    Immutable once created. The price and its line items are stored, never recalculated, so the
    quote shows exactly what the shipper was offered. It records the class table version and the
    tariff version that priced it; booking is rejected if either is no longer current.
    """

    quote_request = models.ForeignKey(QuoteRequest, on_delete=models.PROTECT, related_name="quotes")
    carrier_code = models.CharField(max_length=20)
    carrier_name = models.CharField(max_length=60)
    tariff_version = models.ForeignKey(TariffVersion, on_delete=models.PROTECT)
    # The tariff version's label, copied so the quote reads on its own.
    rate_table_version = models.CharField(max_length=40)
    class_table_version = models.CharField(max_length=40)
    # One price: the customer price (no broker markup yet, so it equals the carrier cost).
    total = models.DecimalField(max_digits=10, decimal_places=2)
    transit_days = models.PositiveSmallIntegerField()
    estimated_delivery_date = models.DateField()
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Quote {self.pk}: {self.carrier_name} ${self.total}"

    def check_bookable(self, now) -> BookableCheck:
        """Can this quote be booked at `now`? Returns the first reason it cannot.

        The caller passes the time in, so tests never depend on the real clock. Four conditions:
        not expired; class table version current; tariff version current; and the request's pickup
        date is still a business day after today (America/Chicago).
        """
        if now >= self.expires_at:
            return BookableCheck(False, "The quote has expired.")
        if self.class_table_version != CLASS_TABLE_VERSION:
            return BookableCheck(False, "The freight class table has changed since this quote.")
        current = TariffVersion.current()
        if current is None or self.tariff_version_id != current.pk:
            return BookableCheck(False, "The rates have changed since this quote.")
        today = timezone.localtime(now).date()
        try:
            pickup.validate_pickup_date(self.quote_request.pickup_date, today)
        except pickup.PickupDateError:
            return BookableCheck(False, "The pickup date is no longer available.")
        return BookableCheck(True)


class QuoteLineItem(ImmutableModel):
    quote = models.ForeignKey(Quote, on_delete=models.PROTECT, related_name="line_items")
    position = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=20)
    description = models.CharField(max_length=100)
    # For accessorials: "auto" or "requested"; empty for line-haul and fuel.
    source = models.CharField(max_length=20, blank=True)
    reason = models.CharField(max_length=150, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["quote_id", "position"]
        constraints = [
            models.UniqueConstraint(fields=["quote", "position"], name="unique_line_position")
        ]

    def __str__(self) -> str:
        return f"{self.description}: ${self.amount}"


class QuotedUnit(ImmutableModel):
    """The freight class used to price one handling unit, snapshotted on the quote."""

    quote = models.ForeignKey(Quote, on_delete=models.PROTECT, related_name="quoted_units")
    handling_unit = models.ForeignKey(HandlingUnit, on_delete=models.PROTECT)
    freight_class = models.CharField(max_length=5)

    class Meta:
        ordering = ["quote_id", "handling_unit_id"]

    def __str__(self) -> str:
        return f"Unit {self.handling_unit_id} priced as class {self.freight_class}"
