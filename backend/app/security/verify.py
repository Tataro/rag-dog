"""Webhook signature verification for Telegram and Line."""
import base64
import hashlib
import hmac

from ..config import settings


def verify_telegram(header_secret: str | None) -> bool:
    expected = settings.telegram_webhook_secret
    if not expected:
        return False
    if header_secret is None:
        return False
    return hmac.compare_digest(header_secret, expected)


def verify_line(body: bytes, signature_b64: str | None) -> bool:
    secret = settings.line_channel_secret
    if not secret or signature_b64 is None:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature_b64)
