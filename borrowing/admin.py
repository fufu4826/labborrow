from django.contrib import admin

from .models import Booking, BorrowItem, BorrowRequest, ConditionImage, Return, ReturnItem


class BorrowItemInline(admin.TabularInline):
    model = BorrowItem
    extra = 0


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0


class ConditionImageInline(admin.TabularInline):
    model = ConditionImage
    extra = 0


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("pk", "user", "equipment", "quantity", "start_at", "end_at", "status")
    list_filter = ("status",)


@admin.register(BorrowRequest)
class BorrowRequestAdmin(admin.ModelAdmin):
    list_display = ("pk", "user", "borrow_at", "due_at", "status")
    list_filter = ("status",)
    inlines = [BorrowItemInline]


@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ("request", "returned_at", "received_by")
    inlines = [ReturnItemInline, ConditionImageInline]
