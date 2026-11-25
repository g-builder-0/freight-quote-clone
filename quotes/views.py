from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from . import contacts, models, serializers
from .bill_of_lading import build_labels
from .booking_service import BookingConflict, book_quote, cancel_booking
from .models import Booking, BookingStatus, HandlingUnit, Quote, QuoteRequest
from .pickup import PickupDateError
from .serializers import (
    BookingSerializer,
    ClassPreviewResultSerializer,
    ClassPreviewSerializer,
    QuoteRequestSerializer,
    QuoteSerializer,
)
from .services import NoTariffError, create_quotes


def quote_queryset():
    return Quote.objects.select_related("quote_request", "tariff_version").prefetch_related(
        "line_items", "quoted_units"
    )


class QuoteRequestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Create, retrieve and list quote requests; create and list the quotes for one request.

    The list is paginated (page size set in settings) and ordered newest first by the model.
    """

    queryset = QuoteRequest.objects.prefetch_related("handling_units")
    serializer_class = QuoteRequestSerializer

    @action(detail=True, methods=["get", "post"], url_path="quotes")
    def quotes(self, request, pk=None):
        """POST: create one quote per carrier for this request, all in one transaction.

        GET: every quote ever made for this request, newest first (expired ones included).
        Both return {"quotes": [...]}. POST needs no body.
        """
        quote_request = self.get_object()  # 404 for an unknown request
        if request.method == "POST":
            try:
                created = create_quotes(quote_request, serializers.get_now())
            except PickupDateError as error:
                return Response({"pickup_date": [str(error)]}, status=status.HTTP_400_BAD_REQUEST)
            except NoTariffError as error:
                return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            # Carrier order (cheap and slow, mid, fast and pricey) is the order they were created.
            quotes = quote_queryset().filter(pk__in=[q.pk for q in created]).order_by("id")
            return Response(
                {"quotes": QuoteSerializer(quotes, many=True).data}, status=status.HTTP_201_CREATED
            )
        # Newest call first; within one call the carrier order (ids ascend with creation).
        quotes = quote_queryset().filter(quote_request=quote_request).order_by("-created_at", "id")
        return Response({"quotes": QuoteSerializer(quotes, many=True).data})


class QuoteViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Retrieve one quote with its line items. Quotes cannot be updated or deleted (405)."""

    queryset = quote_queryset()
    serializer_class = QuoteSerializer

    @action(detail=True, methods=["post"], url_path="bookings")
    def bookings(self, request, pk=None):
        """Book this quote. Body: shipper_contact, receiver_contact, optional special_instructions.

        Order: 404 for an unknown quote, then 400 for a bad body, then 409 for a state conflict.
        """
        quote = self.get_object()
        shipper, receiver, instructions, errors = _booking_input(request.data)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            booking = book_quote(quote, shipper, receiver, instructions, serializers.get_now())
        except BookingConflict as error:
            return _conflict(error)
        booking = Booking.objects.select_related("quote").get(pk=booking.pk)
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)


def _conflict(error: BookingConflict) -> Response:
    return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)


def _contact_errors(data, key: str, clean) -> tuple[object, dict]:
    """Run one contact through `clean`; return (contact, {key: errors}) with errors empty if ok."""
    if key not in data:
        return None, {key: ["This field is required."]}
    if not isinstance(data[key], dict):
        return None, {key: {"non_field_errors": ["Enter the contact as an object."]}}
    contact, errors = clean(data[key])
    return contact, ({key: errors} if errors else {})


def _booking_input(data):
    """Check a booking request body. Returns (shipper, receiver, instructions, errors)."""
    if not isinstance(data, dict):
        return None, None, "", {"non_field_errors": ["Send a JSON object."]}
    shipper, errors = _contact_errors(data, "shipper_contact", contacts.clean_contact)
    receiver, receiver_errors = _contact_errors(data, "receiver_contact", contacts.clean_contact)
    errors.update(receiver_errors)
    instructions, instruction_errors = contacts.clean_instructions(data.get("special_instructions"))
    if instruction_errors:
        errors["special_instructions"] = instruction_errors
    return shipper, receiver, instructions, errors


class BookingViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """One booking, its bill of lading, its pallet labels, and cancellation.

    Bookings cannot be updated or deleted except by cancelling (405). Errors: 400 for a bad body
    (reported first), 404 for an unknown booking, 409 when the booking's state blocks the request.
    """

    queryset = Booking.objects.select_related("quote")
    serializer_class = BookingSerializer

    @action(detail=True, methods=["get"], url_path="bill-of-lading")
    def bill_of_lading(self, request, pk=None):
        """The bill of lading stored when the booking was made (no price or fees)."""
        return Response(self.get_object().bill_of_lading)

    @action(detail=True, methods=["get"], url_path="labels")
    def labels(self, request, pk=None):
        """One label per physical unit, built from the stored bill of lading."""
        booking = self.get_object()
        if booking.status == BookingStatus.CANCELLED:
            return Response(
                {"detail": "Labels are not available for a cancelled booking."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"labels": build_labels(booking.bill_of_lading)})

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancel a booked booking. Body: {"reason": "..."} (required, at most 200 characters)."""
        booking = self.get_object()
        data = request.data if isinstance(request.data, dict) else {}
        reason, errors = contacts.clean_cancel_reason(data.get("reason"))
        if errors:
            return Response({"reason": errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            cancelled = cancel_booking(booking, reason, serializers.get_now())
        except BookingConflict as error:
            return _conflict(error)
        return Response(BookingSerializer(cancelled).data)


class ClassPreviewView(APIView):
    """POST: density and suggested class for one unit's weight and dimensions (Slice 5).

    Calculates only. The unit is built in memory so the model's own `density` and
    `suggested_class` do the work; it is never saved and no quote request is touched.
    """

    def post(self, request):
        serializer = ClassPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        unit = HandlingUnit(**serializer.validated_data)
        return Response(ClassPreviewResultSerializer(unit).data)


class LimitsView(APIView):
    """GET: the limits the front end needs for counters and friendly messages (Slice 5).

    Holds no numbers of its own: each value is read from the constant the validation uses, at
    the moment of the request, so the answer cannot disagree with the rules.
    """

    def get(self, request):
        minimum = models.MIN_UNIT_VALUE
        return Response(
            {
                "unit": {
                    "weight_lb": {"min": minimum, "max": models.MAX_WEIGHT_LB},
                    "length_in": {"min": minimum, "max": models.MAX_LENGTH_IN},
                    "width_in": {"min": minimum, "max": models.MAX_WIDTH_IN},
                    "height_in": {"min": minimum, "max": models.MAX_HEIGHT_IN},
                },
                "text": {
                    "special_instructions_max": contacts.INSTRUCTIONS_MAX_LENGTH,
                    "cancel_reason_max": contacts.CANCEL_REASON_MAX_LENGTH,
                },
            }
        )
