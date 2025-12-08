import os
import uuid
from datetime import datetime, timedelta, timezone

from yookassa import Configuration, Payment

YOOKASSA_ACCOUNT_ID = os.getenv("YOOKASSA_ACCOUNT_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
BASE_URL = os.getenv("BASE_URL", "https://example.com")


def _yk_configure():
    if not YOOKASSA_ACCOUNT_ID or not YOOKASSA_SECRET_KEY:
        raise RuntimeError("YOOKASSA_ACCOUNT_ID/YOOKASSA_SECRET_KEY не заданы")
    Configuration.account_id = str(YOOKASSA_ACCOUNT_ID)
    Configuration.secret_key = str(YOOKASSA_SECRET_KEY)


def _iso_utc(dt: datetime) -> str:
    """ISO-8601 с Z, сек. точность"""
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def create(amount_rub: float, tg_user_id: int) -> tuple[str, str]:
    """
    Создаёт платёж и возвращает (confirmation_url, payment_id).
    TTL = 10 минут.
    """
    _yk_configure()

    value = f"{float(amount_rub):.2f}"
    expires_at = _iso_utc(datetime.now(timezone.utc) + timedelta(minutes=10))
    idemp = str(uuid.uuid4())

    payload = {
        "amount": {"value": value, "currency": "RUB"},
        "capture": True,  # авто-капча при успехе
        "confirmation": {
            "type": "redirect",
            "return_url": f"{BASE_URL}/pay/yookassa/return",
        },
        "description": f"CHESS IT подписка {value}₽ (user {tg_user_id})",
        "metadata": {"tg_user_id": str(tg_user_id)},
        "expires_at": expires_at,
    }

    payment = Payment.create(payload, idempotency_key=idemp)
    url = payment.confirmation.confirmation_url
    return url, payment.id


def check(payment_id: str) -> bool:
    """
    Возвращает True, если платёж успешно оплачен (paid==True / status=='succeeded').
    В остальных случаях False (waiting_for_capture, pending, canceled, refunded...).
    """
    _yk_configure()
    p = Payment.find_one(payment_id)
    status = getattr(p, "status", None)
    paid = bool(getattr(p, "paid", False))
    return paid or status == "succeeded"
