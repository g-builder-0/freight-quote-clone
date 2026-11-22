from rest_framework.routers import DefaultRouter

from .views import QuoteRequestViewSet, QuoteViewSet

router = DefaultRouter()
router.register("quote-requests", QuoteRequestViewSet, basename="quote-request")
router.register("quotes", QuoteViewSet, basename="quote")

urlpatterns = router.urls
