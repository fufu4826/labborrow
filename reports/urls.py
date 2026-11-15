from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("", views.ReportIndexView.as_view(), name="index"),
    path("export/<str:kind>/<str:fmt>/", views.ExportView.as_view(), name="export"),
]
