from decimal import Decimal
from unittest.mock import patch

import razorpay
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .models import Category, DeliveryArea, FoodItem, Order


@override_settings(
    RAZORPAY_KEY_ID="rzp_test_example",
    RAZORPAY_KEY_SECRET="test_secret",
)
class RazorpayCheckoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="buyer",
            password="test-password",
        )
        self.client.force_login(self.user)
        category = Category.objects.create(name="Meals")
        self.food = FoodItem.objects.create(
            name="Rice",
            category=category,
            price=Decimal("12.50"),
            is_available=True,
        )
        DeliveryArea.objects.create(
            pincode="123456",
            city="Test City",
            delivery_charge=Decimal("5.00"),
        )

    def add_food_to_cart(self):
        session = self.client.session
        session["cart"] = {str(self.food.id): 2}
        session.save()

    @patch("food.views.razorpay.Client")
    def test_checkout_creates_gateway_order_with_server_calculated_total(
        self,
        razorpay_client,
    ):
        self.add_food_to_cart()
        razorpay_client.return_value.order.create.return_value = {
            "id": "order_test_123"
        }

        response = self.client.post(
            "/checkout/",
            {
                "customer_name": "Test Buyer",
                "phone": "1234567890",
                "address": "123 Example Street",
                "city": "Test City",
                "pincode": "123456",
                "payment_method": "RAZORPAY",
            },
        )

        order = Order.objects.get(customer=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "razorpay_checkout.html")
        self.assertEqual(order.payment_method, "RAZORPAY")
        self.assertEqual(order.total_amount, Decimal("30.00"))
        self.assertEqual(order.razorpay_order_id, "order_test_123")
        self.assertEqual(order.items.count(), 1)
        self.assertNotEqual(response.context["csrf_token"], "NOTPROVIDED")
        self.assertEqual(
            razorpay_client.return_value.order.create.call_args.kwargs["data"][
                "amount"
            ],
            3000,
        )

    @patch("food.views.razorpay.Client")
    def test_valid_payment_signature_marks_order_paid(self, razorpay_client):
        order = Order.objects.create(
            customer=self.user,
            customer_name="Test Buyer",
            phone="1234567890",
            address="123 Example Street",
            city="Test City",
            pincode="123456",
            payment_method="RAZORPAY",
            payment_status="Pending",
            total_amount=Decimal("30.00"),
            razorpay_order_id="order_test_123",
        )
        session = self.client.session
        session["cart"] = {str(self.food.id): 2}
        session.save()
        (
            razorpay_client.return_value.utility.verify_payment_signature
            .return_value
        ) = True

        response = self.client.post(
            "/payment/razorpay/verify/",
            {
                "local_order_id": str(order.id),
                "razorpay_order_id": "order_test_123",
                "razorpay_payment_id": "pay_test_123",
                "razorpay_signature": "valid_signature",
            },
        )

        order.refresh_from_db()
        self.assertRedirects(
            response,
            f"/order-success/{order.id}/",
            fetch_redirect_response=False,
        )
        self.assertEqual(order.payment_status, "Paid")
        self.assertEqual(order.razorpay_payment_id, "pay_test_123")
        self.assertEqual(self.client.session.get("cart"), {})

    def test_cod_checkout_still_creates_order_and_clears_cart(self):
        self.add_food_to_cart()

        response = self.client.post(
            "/checkout/",
            {
                "customer_name": "Test Buyer",
                "phone": "1234567890",
                "address": "123 Example Street",
                "city": "Test City",
                "pincode": "123456",
                "payment_method": "COD",
            },
        )

        order = Order.objects.get(customer=self.user)
        self.assertRedirects(
            response,
            f"/order-success/{order.id}/",
            fetch_redirect_response=False,
        )
        self.assertEqual(order.payment_method, "COD")
        self.assertEqual(order.total_amount, Decimal("30.00"))
        self.assertEqual(self.client.session.get("cart"), {})

    @patch("food.views.razorpay.Client")
    def test_invalid_payment_signature_does_not_mark_order_paid(
        self,
        razorpay_client,
    ):
        order = Order.objects.create(
            customer=self.user,
            customer_name="Test Buyer",
            phone="1234567890",
            address="123 Example Street",
            city="Test City",
            pincode="123456",
            payment_method="RAZORPAY",
            payment_status="Pending",
            total_amount=Decimal("30.00"),
            razorpay_order_id="order_test_123",
        )
        razorpay_client.return_value.utility.verify_payment_signature.side_effect = (
            razorpay.errors.SignatureVerificationError("invalid signature")
        )

        response = self.client.post(
            "/payment/razorpay/verify/",
            {
                "local_order_id": str(order.id),
                "razorpay_order_id": "order_test_123",
                "razorpay_payment_id": "pay_test_123",
                "razorpay_signature": "invalid_signature",
            },
        )

        order.refresh_from_db()
        self.assertRedirects(
            response,
            "/checkout/",
            fetch_redirect_response=False,
        )
        self.assertEqual(order.payment_status, "Pending")
