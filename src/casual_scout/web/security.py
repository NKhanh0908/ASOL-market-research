from __future__ import annotations

import os
import secrets
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_SESSION_FILE = ".session_secret"
_COOKIE_NAME = "session_id"
_CSRF_COOKIE_NAME = "csrftoken"
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "testserver"}


def allowed_hosts() -> list[str]:
    hosts = set(_ALLOWED_HOSTS)
    for value in os.environ.get('CASUAL_SCOUT_LAN_HOSTS', '').split(','):
        value = value.strip()
        if value:
            address = ip_address(value)
            if address.version != 4 or not address.is_private or address.is_unspecified:
                raise ValueError('CASUAL_SCOUT_LAN_HOSTS requires explicit private IPv4 addresses')
            hosts.add(str(address))
    return sorted(hosts)


def get_or_create_secret(data_dir: Path) -> str:
    secret_path = Path(data_dir) / _SESSION_FILE
    if secret_path.is_file():
        return secret_path.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    secret_path.write_text(secret, encoding="utf-8")
    return secret


class SecurityManager:
    def __init__(self, secret: str) -> None:
        self.serializer = URLSafeTimedSerializer(secret, salt="casual-scout-csrf")

    def generate_csrf_token(self, session_id: str) -> str:
        return self.serializer.dumps({"session_id": session_id})

    def validate_csrf_token(self, token: str, session_id: str, max_age: int = 86400) -> bool:
        try:
            data = self.serializer.loads(token, max_age=max_age)
            return isinstance(data, dict) and data.get("session_id") == session_id
        except (BadSignature, SignatureExpired):
            return False


def is_valid_origin(origin: str | None, hosts=None) -> bool:
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
        return (
            parsed.scheme in ("http", "https")
            and parsed.hostname in (hosts if hosts is not None else _ALLOWED_HOSTS)
        )
    except (ValueError, AttributeError):
        return False


class LocalOriginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, hosts=None):
        super().__init__(app)
        self.hosts = hosts or _ALLOWED_HOSTS

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("Origin")
            referer = request.headers.get("Referer")

            if origin is not None:
                if not is_valid_origin(origin, self.hosts):
                    return Response("Forbidden: Invalid Origin", status_code=403)
            elif referer is not None:
                if not is_valid_origin(referer, self.hosts):
                    return Response("Forbidden: Invalid Referer", status_code=403)
            else:
                return Response("Forbidden: Missing Origin and Referer", status_code=403)

        return await call_next(request)
