"""Seed the first tariff version, RATES-2026-1, with the approved Slice 2 tariff.

All numbers are illustrative and invented (docs/slices/slice_02_quote_engine.md, "Carriers and
tariffs", approved by Graham 2026-11-17). The numbers are written out here, inside the migration,
so this migration keeps producing the same rows even if later code changes.
"""

from decimal import Decimal

from django.db import migrations

LABEL = "RATES-2026-1"

# Weight tiers: under 500, 500-999, 1,000-1,999, 2,000-4,999, 5,000 and up.
BREAKS = ((0, 499), (500, 999), (1000, 1999), (2000, 4999), (5000, None))

# code: (name, rates per tier, minimum, fuel fraction, residential, limited access, liftgate,
#        appointment, transit adjustment in days)
CARRIERS = {
    "cheap": ("Cheap and slow", ("42", "35", "30", "25", "20"), "75", "0.28",
              "85", "95", "65", "40", 1),
    "mid": ("Mid", ("48", "40", "34", "28", "23"), "90", "0.32",
            "100", "120", "85", "50", 0),
    "fast": ("Fast and pricey", ("56", "46", "39", "32", "26"), "110", "0.35",
             "120", "150", "110", "60", -1),
}  # fmt: skip


def seed(apps, schema_editor):
    TariffVersion = apps.get_model("quotes", "TariffVersion")
    CarrierTariff = apps.get_model("quotes", "CarrierTariff")
    WeightBreakRate = apps.get_model("quotes", "WeightBreakRate")
    AccessorialFee = apps.get_model("quotes", "AccessorialFee")

    version = TariffVersion.objects.create(label=LABEL)
    for code, (name, rates, minimum, fuel, residential, limited, liftgate, appointment, adj) in (
        CARRIERS.items()
    ):
        carrier = CarrierTariff.objects.create(
            version=version,
            code=code,
            name=name,
            minimum_charge=Decimal(minimum),
            fuel_percent=Decimal(fuel),
            transit_adjustment_days=adj,
        )
        for (from_lb, to_lb), rate in zip(BREAKS, rates, strict=True):
            WeightBreakRate.objects.create(
                carrier_tariff=carrier,
                from_lb=from_lb,
                to_lb=to_lb,
                rate_per_cwt=Decimal(rate),
            )
        for fee_type, amount in (
            ("residential", residential),
            ("limited_access", limited),
            ("liftgate", liftgate),
            ("appointment", appointment),
        ):
            AccessorialFee.objects.create(
                carrier_tariff=carrier, fee_type=fee_type, amount=Decimal(amount)
            )


def unseed(apps, schema_editor):
    TariffVersion = apps.get_model("quotes", "TariffVersion")
    version = TariffVersion.objects.filter(label=LABEL).first()
    if version is not None:
        for carrier in version.carriers.all():
            carrier.weight_breaks.all().delete()
            carrier.fees.all().delete()
        version.carriers.all().delete()
        version.delete()


class Migration(migrations.Migration):
    dependencies = [("quotes", "0003_quotes_and_tariffs")]
    operations = [migrations.RunPython(seed, unseed)]
