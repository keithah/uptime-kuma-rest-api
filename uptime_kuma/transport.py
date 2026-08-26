"""Transport boundary: ack-style emits over Socket.IO, fake-able in tests."""
import threading

import socketio

from .errors import ConnectionError_, TimeoutError_


class AckTransport:
    """Minimal interface the client needs; fakes subclass this."""

    connected: bool = False

    def connect(self) -> None: ...
    def close(self) -> None: ...
    def emit_ack(self, event, data=None, timeout: float = 15.0): ...
    def on(self, event, handler) -> None: ...


class SocketIOTransport(AckTransport):
    """Real transport against Uptime Kuma's Socket.IO endpoint."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.connected = False
        self._sio = socketio.Client(logger=False, engineio_logger=False)
        self._sio.on("connect", self._on_connect)
        self._sio.on("disconnect", self._on_disconnect)

    def _on_connect(self, *args):
        self.connected = True

    def _on_disconnect(self, *args):
        self.connected = False

    def connect(self) -> None:
        try:
            self._sio.connect(
                self.cfg.url,
                socketio_path=self.cfg.socket_path.lstrip("/"),
                transports=["websocket", "polling"],
                wait_timeout=10,
            )
        except Exception as exc:  # socketio raises many types
            raise ConnectionError_(f"connect to {self.cfg.url} failed: {exc}") from exc

    def close(self) -> None:
        try:
            self._sio.disconnect()
        finally:
            self.connected = False

    def emit_ack(self, event, data=None, timeout: float = 15.0):
        box: dict = {}
        done = threading.Event()

        def cb(*resp):
            box["r"] = resp[0] if resp else None
            done.set()

        try:
            if data is None:
                self._sio.emit(event, callback=cb)
            else:
                self._sio.emit(event, data, callback=cb)
        except Exception as exc:
            raise ConnectionError_(f"emit '{event}' failed: {exc}") from exc

        if not done.wait(timeout):
            raise TimeoutError_(f"no ack for '{event}' within {timeout}s")
        return box.get("r")

    def on(self, event, handler) -> None:
        self._sio.on(event, handler)
