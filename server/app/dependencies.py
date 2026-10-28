"""Server-side session validation and authorization dependencies."""
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from accounting_app.database.connection import DBManager
from accounting_app.database.models import ApiSession, User
from server.app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_session(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="برای دسترسی باید وارد شوید.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    try:
        user_id = UUID(payload["sub"])
        session_id = UUID(payload["sid"])
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="شناسه نشست معتبر نیست.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    now = datetime.now()
    with DBManager():
        session = ApiSession.get_or_none(
            (ApiSession.id == session_id)
            & (ApiSession.user == user_id)
        )
        if session is None or session.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="این نشست فعال نیست یا توسط مدیر لغو شده است.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if session.expires_at <= now:
            session.status = "expired"
            session.revoked_at = now
            session.revocation_reason = "expired"
            session.save(only=[
                ApiSession.status, ApiSession.revoked_at,
                ApiSession.revocation_reason, ApiSession.updated_at,
            ])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="نشست منقضی شده است؛ دوباره وارد شوید.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = User.get_or_none(User.id == user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="حساب کاربری غیرفعال است.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if (
            session.last_seen_at is None
            or now - session.last_seen_at >= timedelta(seconds=60)
        ):
            session.last_seen_at = now
            session.save(only=[ApiSession.last_seen_at, ApiSession.updated_at])
    return session


def get_current_user(session=Depends(get_current_session)):
    with DBManager():
        user = User.get_or_none(User.id == session.user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="حساب کاربری غیرفعال است.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


def require_admin(user=Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="این عملیات فقط برای مدیر مجاز است.",
        )
    return user
