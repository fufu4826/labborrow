from django.contrib import admin

from .models import Category, Equipment


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name_th", "name_en")
    search_fields = ("name_th", "name_en")


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("asset_code", "name_th", "category", "quantity_total", "quantity_out_of_service",
                    "status", "is_active")
    list_filter = ("category", "status", "is_active")
    search_fields = ("asset_code", "name_th", "name_en")
