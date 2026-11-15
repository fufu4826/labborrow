from django.urls import path

from . import views

app_name = "maintenance"

urlpatterns = [
    path("", views.ListView.as_view(), name="list"),
    path("new/", views.CreateView.as_view(), name="create"),
    path("<int:pk>/", views.DetailView.as_view(), name="detail"),
]
