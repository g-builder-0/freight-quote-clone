from rest_framework.routers import DefaultRouter

from .views import BookingViewSet, QuoteRequestViewSet, QuoteViewSet

router = DefaultRouter()
router.register("quote-requests", QuoteRequestViewSet, basename="quote-request")
router.register("quotes", QuoteViewSet, basename="quote")
router.register("bookings", BookingViewSet, basename="booking")

urlpatterns = router.urls
