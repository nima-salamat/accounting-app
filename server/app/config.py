"""Server configuration with a random per-process development signing key."""
import os
import secrets

API_PREFIX = "/api/v1"
TOKEN_TTL_SECONDS = int(os.environ.get("ACCOUNTING_APP_TOKEN_TTL", "28800"))
_CONFIGURED_SECRET = os.environ.get("ACCOUNTING_APP_SECRET_KEY")
# A random fallback avoids a predictable shipped secret. Set a stable secret for remote use.
SIGNING_SECRET = _CONFIGURED_SECRET or secrets.token_urlsafe(48)
