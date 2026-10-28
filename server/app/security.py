"""Signed, time-limited bearer tokens without storing passwords or tokens in the client."""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from fastapi import HTTPException, status

from server.app.config import SIGNING_SECRET, TOKEN_TTL_SECONDS

_serializer = URLSafeTimedSerializer(SIGNING_SECRET, salt="accounting-app-api-v1")


def create_access_token(user_id):
    return _serializer.dumps({"sub": str(user_id)})


def decode_access_token(token):
    try:
        payload = _serializer.loads(token, max_age=TOKEN_TTL_SECONDS)
    except SignatureExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نشست منقضی شده است؛ دوباره وارد شوید.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except BadSignature as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="اعتبار نشست معتبر نیست.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    subject = payload.get("sub") if isinstance(payload, dict) else None
    if not isinstance(subject, str) or not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="اعتبار نشست معتبر نیست.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return subject
