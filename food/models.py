from django.db import models
from django.conf import settings

PAYMENT_METHOD_CHOICES = [
    ("COD", "Cash on Delivery"),
    ("RAZORPAY", "Razorpay"),
]

PAYMENT_STATUS_CHOICES = [
    ("Pending", "Pending"),
    ("Paid", "Paid"),
    ("Failed", "Failed"),
]


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class FoodItem(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="foods"
    )
    price = models.DecimalField(max_digits=8, decimal_places=2)
    image = models.ImageField(
        upload_to="foods/",
        blank=True,
        null=True
    )
    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    def __str__(self):
        return self.name
class Order(models.Model):
    STATUS_CHOICES = [
        ("Placed", "Placed"),
        ("Preparing", "Preparing"),
        ("Out for Delivery", "Out for Delivery"),
        ("Delivered", "Delivered"),
        ("Cancelled", "Cancelled"),
    ]


    customer_name = models.CharField(max_length=100)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="food_orders"
    )
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=100, default="")
    pincode = models.CharField(max_length=6, default="")
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="COD"
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="Pending"
    )
    razorpay_order_id = models.CharField(
        max_length=100,
        blank=True
    )
    razorpay_payment_id = models.CharField(
        max_length=100,
        blank=True
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="Placed"
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"
    


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )
    food = models.ForeignKey(
        FoodItem,
        on_delete=models.PROTECT
    )
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2
    )

    @property
    def subtotal(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.food.name} x {self.quantity}"
    
class DeliveryArea(models.Model):
    pincode = models.CharField(max_length=6, unique=True)
    city = models.CharField(max_length=100)
    is_available = models.BooleanField(default=True)
    delivery_charge = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0
    )

    def __str__(self):
        return f"{self.city} - {self.pincode}"