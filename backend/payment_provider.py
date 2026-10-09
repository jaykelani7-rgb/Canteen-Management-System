"""Razorpay server-side adapter. POST requests are never blindly retried."""
import hashlib
import hmac
import httpx
from fastapi import HTTPException
from config import settings

class RazorpayProvider:
    async def request(self, method, path, payload=None, headers=None):
        if settings.PAYMENT_PROVIDER != "razorpay" or not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise HTTPException(503, "Online payments are not configured")
        async with httpx.AsyncClient(base_url="https://api.razorpay.com/v1/", auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET), timeout=settings.PAYMENT_HTTP_TIMEOUT_SECONDS, follow_redirects=False) as client:
            try:
                response = await client.request(method, path, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError("Unexpected provider response")
                return result
            except (httpx.HTTPError, ValueError):
                raise HTTPException(502, "Payment provider is unavailable; payment must be reconciled") from None

    async def create_order(self, amount, receipt, order_id):
        return await self.request("POST", "orders", {"amount": amount, "currency": "INR", "receipt": receipt, "notes": {"canteen_order_id": str(order_id)}})

    async def fetch_payment(self, payment_id):
        return await self.request("GET", "payments/" + payment_id)

    async def fetch_order(self, order_id):
        return await self.request("GET", "orders/" + order_id)

    async def order_payments(self, order_id):
        return await self.request("GET", "orders/" + order_id + "/payments")

    async def create_refund(self, payment_id, amount, receipt, idempotency_key):
        # Razorpay documents this key for safe retries of precisely this body.
        return await self.request("POST", "payments/" + payment_id + "/refund",
            {"amount": amount, "speed": "normal", "receipt": receipt},
            headers={"X-Refund-Idempotency": idempotency_key})

    async def fetch_refund(self, payment_id, refund_id):
        return await self.request("GET", "payments/" + payment_id + "/refunds/" + refund_id)

    async def payment_refunds(self, payment_id):
        # More than this bounded result requires explicit operator review.
        return await self.request("GET", "payments/" + payment_id + "/refunds?count=100&skip=0")

    def verify_checkout(self, order_id, payment_id, signature):
        expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), (order_id + "|" + payment_id).encode(), hashlib.sha256).hexdigest()
        return bool(settings.RAZORPAY_KEY_SECRET) and hmac.compare_digest(expected, signature)

    def verify_webhook(self, raw, signature):
        expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        return bool(settings.RAZORPAY_WEBHOOK_SECRET) and hmac.compare_digest(expected, signature)

provider = RazorpayProvider()
