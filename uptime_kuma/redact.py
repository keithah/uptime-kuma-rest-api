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


def _is_secret_key(key: str) -> bool:
    """Word-aware secret detection.

    Splits the key on underscores, hyphens and camelCase boundaries and then
    checks for token equality rather than arbitrary substring containment.
    This prevents benign keys like ``headers_count`` or ``token_expiry_days``
    from being falsely classified while still catching ``smtpPassword``,
    ``api_key`` or ``basic_auth_pass``.
    """
    import re as _re

    k = key.strip()
    if not k:
        return False
    # Split camelCase: abcDef -> abc Def
    spaced = _re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", k)
    # Split on non-alphanumeric (underscores, hyphens, dots).
    parts = [p for p in _re.split(r"[^A-Za-z0-9]+", spaced) if p]
    lower_parts = [p.lower() for p in parts]
    joined = "".join(lower_parts)
    normalized_tokens = {t.replace("_", "").lower(): t for t in _SECRET_TOKENS}
    ambiguous_short = {"headers", "token", "secret"}
    for part in lower_parts:
        if part in normalized_tokens:
            # Short ambiguous tokens only count when they are the whole key
            # or the trailing word (e.g. bearer_token), not a prefix like
            # headers_count or token_expiry_days.
            if part in ambiguous_short and len(lower_parts) > 1 and lower_parts[-1] != part:
                continue
            return True
    for norm in normalized_tokens:
        if norm in joined and norm in ("password", "passwd", "bearer", "apikey", "webhookurl", "databaseconnectionstring", "clientsecret", "tlscert", "tlskey", "tlsca", "pushcode", "authvalue"):
            # Distinctive long tokens are safe for substring; short tokens
            # like ``token``/``headers``/``secret`` are not — they would
            # false-positive on ``token_expiry_days`` / ``headers_count`` /
            # ``x-secretless``.
            return True
        # For ``basic_auth`` / ``api_key`` etc. check compound match via parts.
        if "_" in norm or norm in ("authvalue", "pushcode", "tlscert", "tlskey", "tlsca"):
            continue
    # Compound tokens: require constituent words to appear as whole parts.
    if "basic" in lower_parts and "auth" in lower_parts:
        return True
    if "api" in lower_parts and "key" in lower_parts:
        return True
    if "auth" in lower_parts and "value" in lower_parts:
        return True
    if "webhook" in lower_parts and "url" in lower_parts:
        return True
    if "client" in lower_parts and "secret" in lower_parts:
        return True
    return bool("database" in lower_parts and "connection" in lower_parts)


def _scrub_string(value: str) -> str:
    out = _URL_CREDS_RE.sub(r"\1***@", value)
    if "@" not in out:
        return out
    # Bare user:pass@host without a scheme — tighten to avoid mangling
    # ``mailto:ops@example.com`` and ``Time: 10:30@node1``. Require a
    # letter-starting user, a password that contains a letter, and exclude
    # known non-credential schemes.

    def _bare_repl(match: re.Match) -> str:
        user = match.group(1)
        pwd = match.group(2)
        if user.lower() == "mailto":
            return match.group(0)
        # Time-like ``10:30@`` has an all-digit password -> not a credential.
        if pwd.isdigit():
            return match.group(0)
        if not any(c.isalpha() for c in pwd):
            return match.group(0)
        if not user or not user[0].isalpha():
            return match.group(0)
        return "***@"

    return re.sub(r"([A-Za-z0-9._%+-]+):([^@\s/]+)@", _bare_repl, out)


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
