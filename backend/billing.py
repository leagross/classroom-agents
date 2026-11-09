"""Stripe-backed subscriptions.

This has nothing to do with the app's BYOK Anthropic key — users always pay
for their own AI usage directly to Anthropic. What a paid plan buys here is
removal of the free tier's lesson-count limit (and future platform
features), not AI usage itself.

Fully optional: if STRIPE_SECRET_KEY isn't set, every route here degrades to
"billing not configured" and the free-tier lesson limit is never enforced
(there would be no way to upgrade, so it would be unfair to cap anyone).
"""

import os

import stripe
from fastapi import APIRouter, HTTPException, Request

import db

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_PRICE_ID_PREMIUM = os.environ.get("STRIPE_PRICE_ID_PREMIUM", "").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")

FREE_LESSON_LIMIT_PER_MONTH = 3

router = APIRouter()
is_configured = bool(STRIPE_SECRET_KEY and STRIPE_PRICE_ID_PREMIUM)

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def get_plan(user_email: str | None) -> str:
    """'premium' only for a signed-in user with an active paid subscription;
    'free' for everyone else, including anonymous users."""
    if not user_email or not db.is_enabled():
        return "free"
    sub = db.get_subscription(user_email)
    if sub and sub["plan"] == "premium" and sub["status"] == "active":
        return "premium"
    return "free"


def check_lesson_quota(user_email: str | None):
    """Raises HTTPException(402) if a free-tier, signed-in user has hit the
    monthly lesson cap. No-op for anonymous users or when billing isn't
    configured — the cap only makes sense once there's a way to lift it."""
    if not is_configured or not user_email or not db.is_enabled():
        return
    if get_plan(user_email) == "premium":
        return
    count = db.count_lessons_this_month(user_email)
    if count >= FREE_LESSON_LIMIT_PER_MONTH:
        raise HTTPException(
            status_code=402,
            detail=(
                f"הגעת למכסת {FREE_LESSON_LIMIT_PER_MONTH} השיעורים החינמיים לחודש. "
                "שדרג לתוכנית הפרימיום כדי להמשיך ללא הגבלה."
            ),
        )


@router.get("/api/billing/status")
def billing_status(request: Request):
    user = request.session.get("user")
    email = user["email"] if user else None
    plan = get_plan(email)
    used = db.count_lessons_this_month(email) if email and db.is_enabled() else 0
    return {
        "configured": is_configured,
        "signed_in": bool(email),
        "plan": plan,
        "lessons_used_this_month": used,
        "lesson_limit": FREE_LESSON_LIMIT_PER_MONTH if plan == "free" else None,
    }


@router.post("/api/billing/checkout")
async def create_checkout(request: Request):
    if not is_configured:
        raise HTTPException(status_code=503, detail="התשלומים לא מוגדרים עדיין בשרת.")
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="צריך להתחבר כדי לשדרג.")

    body = await request.json()
    if body.get("plan") != "premium":
        raise HTTPException(status_code=400, detail="unknown plan")

    email = user["email"]
    sub = db.get_subscription(email) if db.is_enabled() else None
    customer_id = sub["stripe_customer_id"] if sub else None

    base_url = APP_BASE_URL or str(request.base_url).rstrip("/")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            customer_email=email if not customer_id else None,
            line_items=[{"price": STRIPE_PRICE_ID_PREMIUM, "quantity": 1}],
            success_url=f"{base_url}/app?checkout=success",
            cancel_url=f"{base_url}/pricing?checkout=cancel",
            client_reference_id=email,
            metadata={"user_email": email},
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"שגיאה מול Stripe: {e.user_message or str(e)}")

    return {"url": session.url}


@router.post("/api/billing/webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="webhook not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="invalid webhook signature")

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        email = obj.get("metadata", {}).get("user_email") or obj.get("client_reference_id")
        if email:
            db.upsert_subscription(
                email,
                plan="premium",
                status="active",
                stripe_customer_id=obj.get("customer"),
                stripe_subscription_id=obj.get("subscription"),
            )

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        customer_id = obj.get("customer")
        status = obj.get("status")  # active, canceled, past_due, ...
        plan = "premium" if status == "active" else "free"
        # Look up by customer id isn't modeled as a query here (no index needed
        # for this volume); Stripe always includes metadata on the subscription
        # object when created via our checkout flow.
        email = obj.get("metadata", {}).get("user_email")
        if email:
            db.upsert_subscription(
                email,
                plan=plan,
                status=status or "canceled",
                stripe_customer_id=customer_id,
                stripe_subscription_id=obj.get("id"),
            )

    return {"received": True}
