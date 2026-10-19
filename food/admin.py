from django.contrib import admin
from .models import Category, FoodItem
from .models import Order, OrderItem
from .models import DeliveryArea
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "price",
        "is_available",
        "is_featured",
    )
    list_filter = (
        "category",
        "is_available",
        "is_featured",
    )
    search_fields = ("name",)
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("food", "quantity", "price")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer_name",
        "phone",
        "total_amount",
        "status",
        "created_at",
    )

    list_filter = ("status", "created_at")
    search_fields = ("customer_name", "phone")
    inlines = [OrderItemInline]


@admin.register(DeliveryArea)
class DeliveryAreaAdmin(admin.ModelAdmin):
    list_display = ("pincode", "city", "is_available", "delivery_charge")
    list_filter = ("city", "is_available")
    search_fields = ("pincode", "city")