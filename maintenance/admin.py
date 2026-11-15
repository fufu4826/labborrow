from django.contrib import admin

from .models import DamageReport


@admin.register(DamageReport)
class DamageReportAdmin(admin.ModelAdmin):
    list_display = ("__str__", "equipment", "quantity", "status", "reported_by", "created_at")
    list_filter = ("status", "source")
    search_fields = ("equipment__asset_code", "equipment__name_th", "problem")
