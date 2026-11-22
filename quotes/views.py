from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import serializers
from .models import Quote, QuoteRequest
from .pickup import PickupDateError
from .serializers import QuoteRequestSerializer, QuoteSerializer
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
