"""Authentication and authorization dependencies for protected endpoints."""
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from accounting_app.database.connection import DBManager
from accounting_app.database.models import User
from server.app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="برای دسترسی باید وارد شوید.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    subject = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(subject)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="شناسه نشست معتبر نیست.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    with DBManager():
        user = User.get_or_none(User.id == user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="کاربر نشست دیگر وجود ندارد.",
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
