"""Creating a new tariff version by copying the current one and applying a change file.

A tariff version is immutable once created. A rate change creates a NEW version: every row of the
current version is copied (31 rows for the seeded tariff), the named values are changed in the
copy, and the whole thing is saved in one transaction, so a half-built version is never live and a
bad change file creates nothing.

The change file is JSON that lists only the values to change, for example:

    {"mid": {"fees": {"liftgate": "90.00"}},
     "cheap": {"fuel_percent": "0.30", "weight_breaks": {"1000": "31.00"}}}

Carrier keys are carrier codes. Allowed keys per carrier: "minimum_charge", "fuel_percent",
"transit_adjustment_days", "fees" (by fee type) and "weight_breaks" (by the tier's lower weight).
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import (
    AccessorialFee,
    CarrierTariff,
    TariffVersion,
    WeightBreakRate,
)

CARRIER_FIELDS = ("minimum_charge", "fuel_percent", "transit_adjustment_days")
ALLOWED_KEYS = (*CARRIER_FIELDS, "fees", "weight_breaks")


class TariffChangeError(ValueError):
    """The change file or the request to create a version is not valid. Nothing was created."""


def _decimal(value, where: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise TariffChangeError(f"{where}: {value!r} is not a number.") from error
    if not number.is_finite() or number < 0:
        raise TariffChangeError(f"{where}: {value!r} must be a number that is not negative.")
    return number


def _validate(current: TariffVersion, changes) -> None:
    """Raise TariffChangeError unless every change names something that exists in `current`."""
    if not isinstance(changes, dict):
        raise TariffChangeError("The change file must be a JSON object keyed by carrier code.")
    carriers = {carrier.code: carrier for carrier in current.carriers.all()}
    for code, carrier_changes in changes.items():
        if code not in carriers:
            raise TariffChangeError(f"Unknown carrier {code!r}. Carriers: {sorted(carriers)}.")
        if not isinstance(carrier_changes, dict):
            raise TariffChangeError(f"{code}: changes must be a JSON object.")
        carrier = carriers[code]
        for key, value in carrier_changes.items():
            if key not in ALLOWED_KEYS:
                raise TariffChangeError(f"{code}: unknown field {key!r}. Allowed: {ALLOWED_KEYS}.")
            if key == "transit_adjustment_days":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TariffChangeError(f"{code}.{key}: {value!r} must be a whole number.")
            elif key in ("minimum_charge", "fuel_percent"):
                _decimal(value, f"{code}.{key}")
            elif key == "fees":
                if not isinstance(value, dict):
                    raise TariffChangeError(f"{code}.fees must be a JSON object.")
                allowed = {fee.fee_type for fee in carrier.fees.all()}
                for fee_type, amount in value.items():
                    if fee_type not in allowed:
                        raise TariffChangeError(
                            f"{code}.fees: unknown fee type {fee_type!r}. "
                            f"Allowed: {sorted(allowed)}."
                        )
                    _decimal(amount, f"{code}.fees.{fee_type}")
            else:  # weight_breaks
                if not isinstance(value, dict):
                    raise TariffChangeError(f"{code}.weight_breaks must be a JSON object.")
                allowed = {str(rate.from_lb) for rate in carrier.weight_breaks.all()}
                for from_lb, rate in value.items():
                    if str(from_lb) not in allowed:
                        raise TariffChangeError(
                            f"{code}.weight_breaks: no tier starts at {from_lb!r} lb. "
                            f"Tiers start at: {sorted(allowed, key=int)}."
                        )
                    _decimal(rate, f"{code}.weight_breaks.{from_lb}")


@transaction.atomic
def create_tariff_version(label: str, changes: dict, created_at: datetime | None = None):
    """Copy the current tariff version into a new one named `label` and apply `changes`.

    Returns the new TariffVersion. Raises TariffChangeError, creating nothing, if the label is
    empty or already used, if there is no current version to copy, if `created_at` is not later
    than the current version's (the newest version must be the current one), or if the change file
    names something that does not exist or holds a value that is not valid.
    """
    label = (label or "").strip()
    if not label:
        raise TariffChangeError("The version label must not be empty.")
    if TariffVersion.objects.filter(label=label).exists():
        raise TariffChangeError(f"A tariff version labelled {label!r} already exists.")
    current = TariffVersion.current()
    if current is None:
        raise TariffChangeError("There is no current tariff version to copy.")
    created_at = created_at or timezone.now()
    if created_at <= current.created_at:
        raise TariffChangeError(
            "The new version must be created after the current one "
            f"({current.label}, {current.created_at.isoformat()})."
        )
    _validate(current, changes)

    new_version = TariffVersion.objects.create(label=label, created_at=created_at)
    for carrier in current.carriers.all():
        carrier_changes = changes.get(carrier.code, {})
        values = {
            "minimum_charge": carrier.minimum_charge,
            "fuel_percent": carrier.fuel_percent,
            "transit_adjustment_days": carrier.transit_adjustment_days,
        }
        for field in ("minimum_charge", "fuel_percent"):
            if field in carrier_changes:
                values[field] = _decimal(carrier_changes[field], field)
        if "transit_adjustment_days" in carrier_changes:
            values["transit_adjustment_days"] = carrier_changes["transit_adjustment_days"]
        new_carrier = CarrierTariff.objects.create(
            version=new_version, code=carrier.code, name=carrier.name, **values
        )

        rate_changes = {str(k): v for k, v in carrier_changes.get("weight_breaks", {}).items()}
        for rate in carrier.weight_breaks.all():
            override = rate_changes.get(str(rate.from_lb))
            WeightBreakRate.objects.create(
                carrier_tariff=new_carrier,
                from_lb=rate.from_lb,
                to_lb=rate.to_lb,
                rate_per_cwt=rate.rate_per_cwt if override is None else _decimal(override, "rate"),
            )

        fee_changes = carrier_changes.get("fees", {})
        for fee in carrier.fees.all():
            override = fee_changes.get(fee.fee_type)
            AccessorialFee.objects.create(
                carrier_tariff=new_carrier,
                fee_type=fee.fee_type,
                amount=fee.amount if override is None else _decimal(override, "fee"),
            )
    return new_version


def count_rows(version: TariffVersion) -> int:
    """Rows in a version: the version itself, its carriers, weight-break rates and fees (31)."""
    total = 1
    for carrier in version.carriers.all():
        total += 1 + carrier.weight_breaks.count() + carrier.fees.count()
    return total
