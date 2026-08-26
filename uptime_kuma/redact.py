"""Recursive secret redaction. Total: there is no include-secrets escape hatch."""
import re
from typing import Any

_SECRET_TOKENS = (
    "password", "passwd", "secret", "token", "bearer",
    "api_key", "apikey", "headers", "basic_auth", "authvalue",
    "pushcode", "webhookurl", "tlscert", "tlskey", "tlsca",
    "databaseconnectionstring", "client_secret",
)

_URL_CREDS_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.\-]*://)([^/@:\s]+):([^/@\s]+)@")
_BARE_CREDS_RE = re.compile(r"([A-Za-z0-9._%+-]+):([^@\s/]+)@")


def _is_secret_key(key: str) -> bool:
    k = key.lower()
    return any(tok in k for tok in _SECRET_TOKENS)


def _scrub_string(value: str) -> str:
    out = _URL_CREDS_RE.sub(r"\1***@", value)
    if "@" in out:
        out = _BARE_CREDS_RE.sub("***@", out)
    return out


def redact_value(obj: Any) -> Any:
    """Recursively scrub secret-keyed values and URL-embedded credentials."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _is_secret_key(str(k)):
                out[k] = "***"
            else:
                out[k] = redact_value(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact_value(item) for item in obj]
    if isinstance(obj, str):
        return _scrub_string(obj)
    return obj


NOTIFICATION_FIELDS = ("id", "name", "type", "isDefault", "active", "applyExisting")


def redact_notification(raw: dict) -> dict:
    """Notification listings expose identity fields only — never their config."""
    return {k: raw[k] for k in NOTIFICATION_FIELDS if k in raw}


def redact_monitor(raw: dict) -> dict:
    """Monitors keep useful operational fields; secret-valued keys are masked."""
    return redact_value(dict(raw))


def scrub_credentials_in_text(text: str) -> str:
    """Strip user:pass@ credentials embedded in URLs/strings."""
    return _scrub_string(text)
