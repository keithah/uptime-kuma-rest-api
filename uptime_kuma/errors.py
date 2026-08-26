"""Error taxonomy with stable JSON codes."""


class KumaError(Exception):
    code = "kuma_error"


class AuthError(KumaError):
    code = "auth_error"


class ConnectionError_(KumaError):
    code = "connection_error"


class TimeoutError_(KumaError):
    code = "timeout"
