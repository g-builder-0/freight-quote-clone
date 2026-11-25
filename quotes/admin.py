from django.contrib import admin

from .models import (
    AccessorialFee,
    Booking,
    CarrierTariff,
    Quote,
    QuotedUnit,
    QuoteLineItem,
    TariffVersion,
    WeightBreakRate,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Tariff, quote and booking rows are history: the admin shows them but cannot change them."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (
    TariffVersion,
    CarrierTariff,
    WeightBreakRate,
    AccessorialFee,
    Quote,
    QuoteLineItem,
    QuotedUnit,
    Booking,
):
    admin.site.register(model, ReadOnlyAdmin)
