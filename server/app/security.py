"""Signed access tickets backed by revocable server-side sessions."""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from fastapi import HTTPException, status

from server.app.config import SIGNING_SECRET, TOKEN_TTL_SECONDS

_serializer = URLSafeTimedSerializer(SIGNING_SECRET, salt="accounting-app-api-v1")


def create_access_token(user_id, session_id):
    return _serializer.dumps({
        "sub": str(user_id),
        "sid": str(session_id),
        "kind": "access",
    })


def create_activation_ticket(user_id, session_id):
    return _serializer.dumps({
        "sub": str(user_id),
        "sid": str(session_id),
        "kind": "activation",
    })


def _decode(token, expected_kind):
    try:
        payload = _serializer.loads(token, max_age=TOKEN_TTL_SECONDS)
    except SignatureExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="اعتبار نشست منقضی شده است؛ دوباره وارد شوید.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except BadSignature as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="اعتبار نشست معتبر نیست.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if not isinstance(payload, dict) or payload.get("kind") != expected_kind:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نوع اعتبارنامه معتبر نیست.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not payload.get("sub") or not payload.get("sid"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="اعتبارنامه ناقص است.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def decode_access_token(token):
    return _decode(token, "access")


def decode_activation_ticket(token):
    return _decode(token, "activation")
