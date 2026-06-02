"""Verify Google ID tokens (from native mobile sign-in and web GIS)."""
from fastapi.concurrency import run_in_threadpool
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from ..config import settings


class GoogleAuthError(Exception):
    pass


async def verify_google_id_token(token: str) -> dict:
    """Return the verified claims dict, or raise GoogleAuthError.

    google-auth validates the signature, issuer, and expiry. We additionally
    check the audience against our configured client IDs (web + mobile) and
    require a verified email.
    """
    def _verify() -> dict:
        # A fresh Request() per call: it wraps a requests.Session, which is not
        # thread-safe, and run_in_threadpool may run several of these concurrently.
        request = google_requests.Request()
        # No audience= passed: verify_oauth2_token only accepts a SINGLE audience,
        # but we accept several client IDs (web + mobile). We validate `aud` against
        # the full allowed list ourselves below.
        return id_token.verify_oauth2_token(token, request)

    try:
        info = await run_in_threadpool(_verify)
    except Exception as exc:  # google-auth raises ValueError or GoogleAuthError
        raise GoogleAuthError(str(exc)) from exc

    if info.get("aud") not in settings.google_client_id_list:
        raise GoogleAuthError("token audience not in allowed client IDs")
    if not info.get("email_verified"):
        raise GoogleAuthError("email not verified by Google")
    if not info.get("email"):
        raise GoogleAuthError("token has no email claim")
    return info
