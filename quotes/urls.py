from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BookingViewSet, ClassPreviewView, LimitsView, QuoteRequestViewSet, QuoteViewSet

router = DefaultRouter()
router.register("quote-requests", QuoteRequestViewSet, basename="quote-request")
router.register("quotes", QuoteViewSet, basename="quote")
router.register("bookings", BookingViewSet, basename="booking")

urlpatterns = [
    *router.urls,
    path("class-preview/", ClassPreviewView.as_view(), name="class-preview"),
    path("limits/", LimitsView.as_view(), name="limits"),
]
