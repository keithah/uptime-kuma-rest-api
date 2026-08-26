"""Environment/.env configuration. Credentials never appear in reprs."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from .errors import KumaError


@dataclass
class Config:
    url: str
    username: str
    password: str
    socket_path: str = "/socket.io"
    request_timeout: float = 15.0
    transport_wait: float = 3.0

    def __repr__(self) -> str:  # keep secrets out of logs/tracebacks
        return self.masked().__repr__()

    def masked(self) -> dict:
        return {
            "url": self.url,
            "username": self.username,
            "password": "***",
            "socket_path": self.socket_path,
            "request_timeout": self.request_timeout,
            "transport_wait": self.transport_wait,
        }

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        missing = [
            name
            for name in ("UPTIME_KUMA_URL", "UPTIME_KUMA_USERNAME", "UPTIME_KUMA_PASSWORD")
            if not os.getenv(name)
        ]
        if missing:
            raise KumaError(f"missing required environment variables: {', '.join(missing)}")
        return cls(
            url=os.environ["UPTIME_KUMA_URL"].rstrip("/"),
            username=os.environ["UPTIME_KUMA_USERNAME"],
            password=os.environ["UPTIME_KUMA_PASSWORD"],
            socket_path=os.getenv("UPTIME_KUMA_SOCKET_PATH", "/socket.io"),
            request_timeout=float(os.getenv("UPTIME_KUMA_TIMEOUT", "15")),
        )
