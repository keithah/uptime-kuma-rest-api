"""Small Flask REST adapter around the rewritten Kuma client."""
from flask import Flask, jsonify, request

from .errors import KumaError
from .kuma_client import KumaClient


def create_client() -> KumaClient:
    return KumaClient()


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    if config:
        app.config.update(config)

    @app.errorhandler(KumaError)
    def handle_kuma_error(exc: KumaError):
        status = {
            "auth_error": 401,
            "connection_error": 503,
            "timeout": 504,
        }.get(exc.code, 404)
        return jsonify({"code": exc.code, "error": str(exc)}), status

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):
        app.logger.exception("unexpected Kuma API error")
        return jsonify({"code": "internal_error", "error": str(exc)}), 500

    @app.get("/health")
    def health():
        result = create_client().health()
        return jsonify({"service": "uptime-kuma", **result})

    @app.get("/incident-context")
    def incident_context():
        monitor = request.args.get("monitor", "").strip()
        if not monitor:
            return jsonify({"code": "invalid_request", "error": "monitor is required"}), 400
        raw = request.args.get("lookback_minutes", "60")
        try:
            lookback = int(raw)
        except ValueError:
            return jsonify({"code": "invalid_request", "error": "lookback_minutes must be an integer"}), 400
        if lookback < 1 or lookback > 24 * 60:
            return jsonify({"code": "invalid_request", "error": "lookback_minutes must be 1..1440"}), 400
        return jsonify(create_client().incident_context(monitor, lookback_minutes=lookback))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
