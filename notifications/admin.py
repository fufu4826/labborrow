from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "event", "status", "attempts")
    list_filter = ("status", "event")
    search_fields = ("user__username", "message")
    readonly_fields = ("retry_key",)
