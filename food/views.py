import logging
from decimal import Decimal, InvalidOperation

import razorpay
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Category, DeliveryArea, FoodItem, Order, OrderItem


logger = logging.getLogger(__name__)

def home(request):
    categories = Category.objects.all().order_by("name")

    all_available_foods = (
        FoodItem.objects
        .filter(is_available=True)
        .select_related("category")
    )

    foods = all_available_foods

    search = request.GET.get("q", "").strip()
    if search:
        foods = foods.filter(name__icontains=search)

    category_id = request.GET.get("category", "").strip()
    if category_id.isdigit():
        foods = foods.filter(category_id=int(category_id))

    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()

    min_value = None
    max_value = None
    filter_error = ""

    try:
        if min_price:
            min_value = Decimal(min_price)
            if not min_value.is_finite() or min_value < 0:
                raise InvalidOperation

        if max_price:
            max_value = Decimal(max_price)
            if not max_value.is_finite() or max_value < 0:
                raise InvalidOperation

    except (InvalidOperation, ValueError):
        min_value = None
        max_value = None
        filter_error = "Please enter valid non-negative prices."

    if not filter_error:
        if (
            min_value is not None
            and max_value is not None
            and min_value > max_value
        ):
            filter_error = (
                "Minimum price cannot exceed maximum price."
            )
            foods = foods.none()
        else:
            if min_value is not None:
                foods = foods.filter(price__gte=min_value)

            if max_value is not None:
                foods = foods.filter(price__lte=max_value)

    selected_sort = request.GET.get("sort", "name_az")

    if selected_sort == "price_low":
        foods = foods.order_by("price", "name")
    elif selected_sort == "price_high":
        foods = foods.order_by("-price", "name")
    else:
        selected_sort = "name_az"
        foods = foods.order_by("name")

    featured_foods = all_available_foods.filter(
        is_featured=True
    ).order_by("-id")[:6]

    context = {
        "categories": categories,
        "foods": foods,
        "featured_foods": featured_foods,
        "search": search,
        "selected_category": category_id,
        "min_price": min_price,
        "max_price": max_price,
        "selected_sort": selected_sort,
        "filter_error": filter_error,
    }

    return render(request, "home.html", context)
def get_cart_count(request):
    cart = request.session.get("cart", {})
    return sum(cart.values())


@require_POST
def add_to_cart(request, food_id):
    food = get_object_or_404(
        FoodItem,
        id=food_id,
        is_available=True
    )

    cart = request.session.get("cart", {})
    food_key = str(food.id)

    cart[food_key] = cart.get(food_key, 0) + 1

    request.session["cart"] = cart
    request.session.modified = True

    return redirect("cart")


def cart(request):
    cart_data = request.session.get("cart", {})
    items = []
    total = 0

    for food_id, quantity in cart_data.items():
        food = FoodItem.objects.filter(
            id=food_id,
            is_available=True
        ).first()

        if food is None or not isinstance(quantity, int) or quantity < 1:
            continue

        subtotal = food.price * quantity
        total += subtotal

        items.append({
            "food": food,
            "quantity": quantity,
            "subtotal": subtotal,
        })

    return render(request, "cart.html", {
        "items": items,
        "total": total,
    })


@require_POST
def update_cart(request, food_id):
    cart_data = request.session.get("cart", {})
    food_key = str(food_id)

    try:
        quantity = int(request.POST.get("quantity", "1"))
    except (ValueError, TypeError):
        return redirect("cart")

    food = get_object_or_404(FoodItem, id=food_id)

    if not food.is_available or quantity <= 0:
        cart_data.pop(food_key, None)
    else:
        cart_data[food_key] = min(quantity, 99)

    request.session["cart"] = cart_data
    request.session.modified = True

    return redirect("cart")


@require_POST
def remove_from_cart(request, food_id):
    cart_data = request.session.get("cart", {})
    cart_data.pop(str(food_id), None)

    request.session["cart"] = cart_data
    request.session.modified = True

    return redirect("cart")


@login_required
def checkout(request):
    cart_data = request.session.get("cart", {})

    if not cart_data:
        messages.error(request, "Your cart is empty.")
        return redirect("cart")

    items = []
    total = Decimal("0.00")

    for food_id, quantity in cart_data.items():
        if not isinstance(quantity, int) or not 1 <= quantity <= 99:
            messages.error(request, "Invalid cart quantity.")
            return redirect("cart")

        food = FoodItem.objects.filter(
            id=food_id,
            is_available=True
        ).first()

        if food is None:
            messages.error(
                request,
                "A food item is unavailable. Please check your cart."
            )
            return redirect("cart")

        subtotal = food.price * quantity
        total += subtotal

        items.append({
            "food": food,
            "quantity": quantity,
            "subtotal": subtotal,
        })

    delivery_charge = Decimal("0.00")
    grand_total = total
    pincode = (
        request.POST.get("pincode", "").strip()
        if request.method == "POST"
        else ""
    )

    if pincode.isdigit() and len(pincode) == 6:
        delivery_area = DeliveryArea.objects.filter(
            pincode=pincode,
            is_available=True
        ).first()

        if delivery_area:
            delivery_charge = delivery_area.delivery_charge

    grand_total = total + delivery_charge

    if request.method == "POST":
        name = request.POST.get("customer_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        address = request.POST.get("address", "").strip()
        city = request.POST.get("city", "").strip()
        pincode = request.POST.get("pincode", "").strip()
        payment_method = request.POST.get("payment_method", "COD").strip()

        # Validate customer details
        if not name or len(name) > 100:
            messages.error(
                request,
                "Please enter a valid name."
            )
            return redirect("checkout")

        if not phone.isdigit() or len(phone) != 10:
            messages.error(
                request,
                "Please enter a valid 10-digit phone number."
            )
            return redirect("checkout")

        if len(address) < 10 or not city:
            messages.error(
                request,
                "Please enter a complete delivery address and city."
            )
            return redirect("checkout")

        # Validate PIN code
        if len(pincode) != 6 or not pincode.isdigit():
            messages.error(
                request,
                "Please enter a valid 6-digit PIN code."
            )
            return redirect("checkout")

        # Allow only supported payment methods
        if payment_method not in {"COD", "RAZORPAY"}:
            messages.error(request, "Invalid payment method.")
            return redirect("checkout")

        # Verify delivery availability on the server
        delivery_area = DeliveryArea.objects.filter(
            pincode=pincode,
            is_available=True
        ).first()

        if delivery_area is None:
            messages.error(
                request,
                "Delivery is not available at this PIN code."
            )
            return redirect("checkout")

        # Calculate amount on the server, not from browser input
        delivery_charge = delivery_area.delivery_charge
        grand_total = total + delivery_charge

        if payment_method == "RAZORPAY":
            if (
                not settings.RAZORPAY_KEY_ID
                or not settings.RAZORPAY_KEY_SECRET
            ):
                messages.error(
                    request,
                    "Payment gateway is not configured."
                )
                return redirect("checkout")

            with transaction.atomic():
                order = Order.objects.create(
                    customer=request.user,
                    customer_name=name,
                    phone=phone,
                    address=address,
                    city=city,
                    pincode=pincode,
                    payment_method="RAZORPAY",
                    payment_status="Pending",
                    total_amount=grand_total,
                )

                for item in items:
                    OrderItem.objects.create(
                        order=order,
                        food=item["food"],
                        quantity=item["quantity"],
                        price=item["food"].price,
                    )

            client = razorpay.Client(
                auth=(
                    settings.RAZORPAY_KEY_ID,
                    settings.RAZORPAY_KEY_SECRET,
                )
            )
            amount_paise = int(grand_total * 100)

            try:
                razorpay_order = client.order.create(
                    data={
                        "amount": amount_paise,
                        "currency": "INR",
                        "receipt": f"FD-{order.id}",
                        "notes": {
                            "local_order_id": str(order.id)
                        },
                    }
                )
            except (
                razorpay.errors.BadRequestError,
                razorpay.errors.GatewayError,
                razorpay.errors.ServerError,
                requests.exceptions.RequestException,
            ):
                logger.exception(
                    "Could not create Razorpay order for local order %s",
                    order.id,
                )
                order.payment_status = "Failed"
                order.save(update_fields=["payment_status"])
                messages.error(
                    request,
                    "Could not start online payment. Please try COD or retry."
                )
                return redirect("checkout")

            order.razorpay_order_id = razorpay_order["id"]
            order.save(update_fields=["razorpay_order_id"])

            return render(
                request,
                "razorpay_checkout.html",
                {
                    "order": order,
                    "razorpay_key_id": settings.RAZORPAY_KEY_ID,
                    "razorpay_order_id": razorpay_order["id"],
                    "amount_paise": amount_paise,
                },
            )

        with transaction.atomic():
            order = Order.objects.create(
                customer_name=name,
                customer=request.user,
                phone=phone,
                address=address,
                city=city,
                pincode=pincode,
                payment_method="COD",
                payment_status="Pending",
                total_amount=grand_total,
            )

            for item in items:
                OrderItem.objects.create(
                    order=order,
                    food=item["food"],
                    quantity=item["quantity"],
                    price=item["food"].price,
                )

        request.session["cart"] = {}
        request.session.modified = True

        return redirect("order_success", order_id=order.id)

    return render(request, "checkout.html", {
        "items": items,
        "total": total,
        "delivery_charge": delivery_charge,
        "grand_total": grand_total,
    })


@login_required
@require_POST
def verify_razorpay_payment(request):
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        messages.error(request, "Payment gateway is not configured.")
        return redirect("checkout")

    local_order_id = request.POST.get("local_order_id", "").strip()
    razorpay_order_id = request.POST.get("razorpay_order_id", "").strip()
    razorpay_payment_id = request.POST.get("razorpay_payment_id", "").strip()
    razorpay_signature = request.POST.get("razorpay_signature", "").strip()

    order = get_object_or_404(
        Order,
        id=local_order_id,
        customer=request.user,
        payment_method="RAZORPAY",
    )

    if order.payment_status == "Paid":
        if order.razorpay_payment_id == razorpay_payment_id:
            return redirect("order_success", order_id=order.id)
        messages.error(request, "This payment has already been processed.")
        return redirect("checkout")

    if (
        order.payment_status != "Pending"
        or not razorpay_payment_id
        or not razorpay_signature
        or razorpay_order_id != order.razorpay_order_id
    ):
        messages.error(request, "Could not verify the online payment.")
        return redirect("checkout")

    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET,
        )
    )
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
        )
    except razorpay.errors.SignatureVerificationError:
        logger.warning(
            "Razorpay signature verification failed for local order %s",
            order.id,
        )
        messages.error(request, "Could not verify the online payment.")
        return redirect("checkout")

    order.payment_status = "Paid"
    order.razorpay_payment_id = razorpay_payment_id
    order.save(update_fields=["payment_status", "razorpay_payment_id"])
    request.session["cart"] = {}
    request.session.modified = True

    return redirect("order_success", order_id=order.id)


@login_required
def order_success(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        customer=request.user
    )

    return render(
        request,
        "order_success.html",
        {"order": order}
    )

def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = UserCreationForm()

    return render(request, "signup.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            login(request, form.get_user())
            return redirect("home")
    else:
        form = AuthenticationForm()

    return render(request, "login.html", {"form": form})


def logout_view(request):
    if request.method == "POST":
        logout(request)

    return redirect("home")


@login_required
def my_orders(request):
    orders = Order.objects.filter(
        customer=request.user
    ).order_by("-created_at")

    return render(request, "my_orders.html", {"orders": orders})

@staff_member_required
def order_dashboard(request):
    orders = Order.objects.all().order_by("-created_at")

    status_filter = request.GET.get("status", "")
    if status_filter in dict(Order.STATUS_CHOICES):
        orders = orders.filter(status=status_filter)

    total_orders = Order.objects.count()
    placed_orders = Order.objects.filter(status="Placed").count()
    delivered_orders = Order.objects.filter(status="Delivered").count()
    cancelled_orders = Order.objects.filter(status="Cancelled").count()

    context = {
        "orders": orders,
        "status_choices": Order.STATUS_CHOICES,
        "selected_status": status_filter,
        "total_orders": total_orders,
        "placed_orders": placed_orders,
        "delivered_orders": delivered_orders,
        "cancelled_orders": cancelled_orders,
    }
    return render(request, "order_dashboard.html", context)

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__food"),
        id=order_id,
        customer=request.user
    )

    return render(
        request,
        "order_detail.html",
        {"order": order}
    )

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__food"),
        id=order_id,
        customer=request.user
    )

    order_items = []
    for item in order.items.all():
        order_items.append({
            "food_name": item.food.name,
            "price": item.price,
            "quantity": item.quantity,
            "subtotal": item.price * item.quantity,
        })

    return render(
        request,
        "order_detail.html",
        {
            "order": order,
            "order_items": order_items,
        }
    )

def check_delivery(request):
    pincode = request.GET.get("pincode", "").strip()

    if len(pincode) != 6 or not pincode.isdigit():
        return JsonResponse({
            "available": False,
            "message": "Please enter a valid 6-digit PIN code."
        })

    area = DeliveryArea.objects.filter(
        pincode=pincode,
        is_available=True
    ).first()

    if area:
        return JsonResponse({
            "available": True,
            "message": f"Delivery is available in {area.city}.",
            "delivery_charge": str(area.delivery_charge)
        })

    return JsonResponse({
        "available": False,
        "message": "Sorry, delivery is not available in this area."
    })


@login_required
@require_POST
def cancel_order(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        customer=request.user
    )

    if order.status == "Delivered":
        messages.error(
            request,
            "Delivered order cannot be cancelled."
        )

    elif order.status == "Cancelled":
        messages.info(
            request,
            "This order is already cancelled."
        )

    elif order.status != "Placed":
        messages.error(
            request,
            "Order cannot be cancelled after preparation starts."
        )

    else:
        order.status = "Cancelled"
        order.save(update_fields=["status"])

        messages.success(
            request,
            "Your order has been cancelled successfully."
        )

    return redirect("my_orders")
@login_required
@require_POST
def verify_razorpay_payment(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        customer=request.user,
        payment_method="RAZORPAY",
    )

    success_url = reverse("order_success", args=[order.id])

    # Allow a repeated successful callback safely
    if order.payment_status == "Paid":
        return JsonResponse({
            "success": True,
            "redirect_url": success_url,
        })

    payment_id = request.POST.get("razorpay_payment_id", "").strip()
    submitted_order_id = request.POST.get(
        "razorpay_order_id", ""
    ).strip()
    signature = request.POST.get(
        "razorpay_signature", ""
    ).strip()

    if not payment_id or not submitted_order_id or not signature:
        return JsonResponse(
            {
                "success": False,
                "message": "Missing payment verification details.",
            },
            status=400,
        )

    # Match callback order ID against the server-stored ID
    if submitted_order_id != order.razorpay_order_id:
        return JsonResponse(
            {
                "success": False,
                "message": "Order ID verification failed.",
            },
            status=400,
        )

    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET,
        )
    )

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": order.razorpay_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })

        payment = client.payment.fetch(payment_id)

    except Exception:
        return JsonResponse(
            {
                "success": False,
                "message": "Payment verification failed.",
            },
            status=400,
        )

    # Check the payment belongs to this Razorpay order
    if payment.get("order_id") != order.razorpay_order_id:
        return JsonResponse(
            {
                "success": False,
                "message": "Payment does not match this order.",
            },
            status=400,
        )

    expected_amount = int(order.total_amount * 100)

    if (
        payment.get("amount") != expected_amount
        or payment.get("currency") != "INR"
    ):
        return JsonResponse(
            {
                "success": False,
                "message": "Payment amount verification failed.",
            },
            status=400,
        )

    # Do not mark an uncaptured payment as Paid
    if payment.get("status") != "captured":
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Payment is not captured yet. "
                    "Check Razorpay capture settings."
                ),
            },
            status=400,
        )

    order.payment_status = "Paid"
    order.razorpay_payment_id = payment_id
    order.save(update_fields=[
        "payment_status",
        "razorpay_payment_id",
    ])

    # Clear cart only after verified successful payment
    request.session["cart"] = {}
    request.session.modified = True

    return JsonResponse({
        "success": True,
        "redirect_url": success_url,
    })