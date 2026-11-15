from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.EquipmentListView.as_view(), name="list"),
    path("new/", views.EquipmentCreateView.as_view(), name="create"),
    path("import/", views.EquipmentImportView.as_view(), name="import"),
    path("import/template.xlsx", views.ImportTemplateView.as_view(), name="import_template"),
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),
    path("<int:pk>/", views.EquipmentDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.EquipmentUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.EquipmentDeleteView.as_view(), name="delete"),
]
