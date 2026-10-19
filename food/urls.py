from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("cart/", views.cart, name="cart"),
    path(
        "cart/add/<int:food_id>/",
        views.add_to_cart,
        name="add_to_cart"
    ),
    path(
        "cart/update/<int:food_id>/",
        views.update_cart,
        name="update_cart"
    ),
    path(
        "cart/remove/<int:food_id>/",
        views.remove_from_cart,
        name="remove_from_cart"
    ),
    path("checkout/", views.checkout, name="checkout"),
    path(
        "payment/razorpay/verify/",
        views.verify_razorpay_payment,
        name="verify_razorpay_payment",
    ),
    path(
        "order-success/<int:order_id>/",
        views.order_success,
        name="order_success",
    ),
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("my-orders/", views.my_orders, name="my_orders"),
    path("order-dashboard/", views.order_dashboard, name="order_dashboard"),
    path(
    "my-orders/<int:order_id>/",
    views.order_detail,
    name="order_detail"
   ),
    path("check-delivery/", views.check_delivery, name="check_delivery"),
    
    path(
    "cancel-order/<int:order_id>/",
    views.cancel_order,
    name="cancel_order"
    ),
    path(
    "payment/razorpay/verify/<int:order_id>/",
    views.verify_razorpay_payment,
    name="verify_razorpay_payment",
),



]