from django.urls import path

from quotes.views import RequestQuoteListView

from .views import DisputeResolutionView, ServiceRequestListCreateView, ServiceRequestTransitionView

urlpatterns = [
    path("", ServiceRequestListCreateView.as_view()),
    path("<int:pk>/transition/", ServiceRequestTransitionView.as_view()),
    path("<int:request_id>/quotes/", RequestQuoteListView.as_view()),
    path("<int:pk>/resolve-dispute/", DisputeResolutionView.as_view()),
]
