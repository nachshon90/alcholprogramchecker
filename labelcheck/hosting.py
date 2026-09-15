"""Guards that only matter when the tool is reachable from the internet.

Run on your own machine, this application is a single-user local tool: it
binds to 127.0.0.1, has no login, and nothing it handles leaves the computer.
Putting it on a public address changes every one of those assumptions, so
this module adds what that move requires:

  * a password, enforced before anything expensive happens
  * a rate limit, because OCR is CPU-heavy and an open endpoint is a target
  * correct client addresses and HTTPS detection behind a reverse proxy

None of it is active for a local run. The functions here do nothing unless a
password is configured, so the local experience is unchanged.

Be clear-eyed about the trade-off: once this is hosted, label artwork and
company details travel over the network to a third-party server. The claim
the tool makes locally - that nothing leaves your computer - is no longer
true, and the wording on the hosted pages changes to say so.
"""
import hmac
import os
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Deque, Dict, Optional

from flask import Response, request

# --- Password -------------------------------------------------------------
PASSWORD_ENV = "LABELCHECK_PASSWORD"
REALM = "Alcohol Label Compliance Checker"


def configured_password() -> Optional[str]:
    value = os.environ.get(PASSWORD_ENV, "").strip()
    return value or None


def is_public_mode() -> bool:
    """True when a password is set, which is what hosting requires."""
    return configured_password() is not None


def _password_matches(supplied: Optional[str]) -> bool:
    expected = configured_password()
    if expected is None:
        return True
    if supplied is None:
        return False
    # Constant-time comparison: a plain == leaks the password one character
    # at a time through response timing.
    return hmac.compare_digest(supplied.encode("utf-8"),
                               expected.encode("utf-8"))


def _unauthorized() -> Response:
    response = Response(
        "This checker is password protected. Please enter the password you "
        "were given.",
        401,
        {"WWW-Authenticate": f'Basic realm="{REALM}", charset="UTF-8"'},
    )
    return response


def check_password() -> Optional[Response]:
    """Enforce the password, if one is configured. Returns a 401 or None."""
    if not is_public_mode():
        return None
    auth = request.authorization
    supplied = auth.password if auth and auth.password else None
    # Allow the password to be sent as the username too, which is friendlier
    # for people pasting into a browser prompt.
    if supplied is None and auth and auth.username:
        supplied = auth.username
    return None if _password_matches(supplied) else _unauthorized()


# --- Rate limiting --------------------------------------------------------
# OCR takes real CPU time, so an unauthenticated flood would be an easy
# denial of service. These limits are deliberately generous for a person
# working through a stack of labels, and restrictive for a script.
WINDOW_SECONDS = float(os.environ.get("LABELCHECK_RATE_WINDOW", "300"))
MAX_REQUESTS = int(os.environ.get("LABELCHECK_RATE_MAX", "40"))

_hits: Dict[str, Deque[float]] = defaultdict(deque)
# Stops the table growing without bound if many addresses appear.
_MAX_TRACKED = 2048


def client_address() -> str:
    """The caller's address, trusting proxy headers only when told to."""
    return request.remote_addr or "unknown"


def _too_many(address: str) -> bool:
    now = time.monotonic()
    seen = _hits[address]
    cutoff = now - WINDOW_SECONDS
    while seen and seen[0] < cutoff:
        seen.popleft()
    if len(seen) >= MAX_REQUESTS:
        return True
    seen.append(now)
    if len(_hits) > _MAX_TRACKED:
        for key in [k for k, v in list(_hits.items()) if not v][:512]:
            _hits.pop(key, None)
    return False


def rate_limited(view):
    """Apply the rate limit to an expensive endpoint. No-op when local."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if is_public_mode() and _too_many(client_address()):
            return Response(
                "Too many checks from this address. Please wait a few "
                "minutes and try again.",
                429,
                {"Retry-After": str(int(WINDOW_SECONDS))},
            )
        return view(*args, **kwargs)
    return wrapper


def reset_rate_limits() -> None:
    """Used by the tests."""
    _hits.clear()


# --- Behind a reverse proxy ----------------------------------------------
def trust_proxy(flask_app, hops: int = 1) -> None:
    """Read the real scheme and client address from the proxy's headers.

    Hosts such as Render, Fly.io and Heroku terminate HTTPS in front of the
    application. Without this the app sees every request as plain HTTP from
    the proxy's own address, which breaks generated links and makes the rate
    limit count the whole internet as one caller.

    Only enable this when something trustworthy really is in front, because
    these headers are trivially forged by a direct caller.
    """
    from werkzeug.middleware.proxy_fix import ProxyFix
    flask_app.wsgi_app = ProxyFix(
        flask_app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops, x_prefix=0)


def extra_headers(secure: bool) -> Dict[str, str]:
    """Headers that only apply to a hosted, HTTPS deployment."""
    if not secure:
        return {}
    return {
        # Two years, and tell browsers never to fall back to plain HTTP.
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    }
