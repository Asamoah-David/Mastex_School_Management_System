from django.contrib import admin
from .models import (
    StudentAttendance,
    CanteenItem,
    CanteenPayment,
    BusRoute,
    BusPayment,
    Textbook,
    TextbookSale,
)


@admin.register(StudentAttendance)
class StudentAttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "date", "status", "school")
    list_filter = ("school", "status", "date")


@admin.register(CanteenItem)
class CanteenItemAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "school", "is_available")


@admin.register(CanteenPayment)
class CanteenPaymentAdmin(admin.ModelAdmin):
    list_display = ("student", "amount", "payment_date", "school")


@admin.register(BusRoute)
class BusRouteAdmin(admin.ModelAdmin):
    list_display = ("name", "fee_per_term", "school")


@admin.register(BusPayment)
class BusPaymentAdmin(admin.ModelAdmin):
    list_display = ("student", "amount", "term_period", "paid", "school")


@admin.register(Textbook)
class TextbookAdmin(admin.ModelAdmin):
    list_display = ("title", "price", "stock", "school")


@admin.register(TextbookSale)
class TextbookSaleAdmin(admin.ModelAdmin):
    list_display = ("student", "textbook", "quantity", "amount", "sale_date", "school")
