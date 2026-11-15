from django.urls import path

from . import views

app_name = "borrowing"

urlpatterns = [
    path("calendar/", views.calendar, name="calendar"),
    path("calendar/events/", views.calendar_events, name="calendar_events"),
    path("book/<int:equipment_pk>/", views.booking_create, name="booking_create"),
    path("bookings/<int:pk>/cancel/", views.booking_cancel, name="booking_cancel"),
    path("bookings/<int:pk>/convert/", views.booking_convert, name="booking_convert"),
    path("request/new/", views.request_create, name="request_create"),
    path("mine/", views.my_requests, name="my_requests"),
    path("requests/<int:pk>/", views.request_detail, name="request_detail"),
    path("requests/<int:pk>/cancel/", views.request_cancel, name="request_cancel"),
    path("staff/requests/", views.staff_requests, name="staff_requests"),
    path("requests/<int:pk>/approve/", views.request_approve, name="request_approve"),
    path("requests/<int:pk>/reject/", views.request_reject, name="request_reject"),
    path("requests/<int:pk>/hand-over/", views.request_hand_over, name="request_hand_over"),
    path("requests/<int:pk>/return/", views.request_return, name="request_return"),
    path("history/", views.history, name="history"),
]
