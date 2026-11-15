from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AppUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Lab", {"fields": ("role", "student_id", "phone", "department", "language", "line_user_id")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Lab", {"fields": ("role", "student_id", "phone", "department")}),
    )
    list_display = ("username", "get_full_name", "email", "role", "is_active")
    list_filter = UserAdmin.list_filter + ("role",)
    search_fields = UserAdmin.search_fields + ("student_id",)
