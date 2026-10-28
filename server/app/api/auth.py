"""First-run setup, login, activation waiting, and logout lifecycle."""
import hmac
import os
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from accounting_app.database.connection import DBManager
from accounting_app.database.models import ApiSession, User
from accounting_app.services.authentication import AuthManager
from accounting_app.services.installer import complete_initial_setup, is_setup_required
from server.app.config import TOKEN_TTL_SECONDS
from server.app.dependencies import get_current_session, get_current_user
from server.app.schemas import (
    LoginRequest, LoginResponse, SessionStatusRequest, SetupRequest,
)
from server.app.security import (
    create_access_token, create_activation_ticket, decode_activation_ticket,
)

router = APIRouter(tags=["authentication"])


def _user_payload(user):
    return {
        "id": str(user.id),
        "username": user.username,
        "is_admin": bool(user.is_admin),
        "buttons": user.buttons,
        "is_active": bool(user.is_active),
        "requires_session_activation": bool(user.requires_session_activation),
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _request_metadata(request, client_name):
    return {
        "client_name": client_name or "Desktop client",
        "remote_addr": request.client.host if request.client is not None else None,
        "user_agent": (request.headers.get("user-agent") or "")[:256] or None,
    }


def _new_session(user, request, client_name, status_value):
    now = datetime.now()
    metadata = _request_metadata(request, client_name)
    with DBManager():
        session = ApiSession.create(
            user=user.id,
            status=status_value,
            expires_at=now + timedelta(seconds=TOKEN_TTL_SECONDS),
            last_seen_at=now if status_value == "active" else None,
            activated_at=now if status_value == "active" else None,
            **metadata,
        )
    return session


@router.get("/setup/status")
def setup_status():
    return {"setup_required": is_setup_required()}


def _authorize_setup(request, payload):
    configured_token = os.environ.get("ACCOUNTING_APP_SETUP_TOKEN")
    host = request.client.host if request.client is not None else ""
    is_local = host in ("127.0.0.1", "::1", "localhost", "testclient")
    if configured_token:
        supplied = (payload.setup_token or "").encode("utf-8")
        expected = configured_token.encode("utf-8")
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=403, detail="توکن نصب اولیه معتبر نیست.")
    elif not is_local:
        raise HTTPException(
            status_code=403,
            detail="برای نصب اولیه از راه دور، ACCOUNTING_APP_SETUP_TOKEN را تنظیم کنید.",
        )


@router.post("/setup", status_code=status.HTTP_201_CREATED)
def setup(payload: SetupRequest, request: Request):
    if not is_setup_required():
        raise HTTPException(status_code=409, detail="نصب اولیه قبلاً انجام شده است.")
    _authorize_setup(request, payload)
    try:
        user = complete_initial_setup(
            payload.username,
            payload.password,
            payload.password_confirmation,
            payload.schema_rows,
            payload.company_name,
            payload.business_profile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session = _new_session(user, request, "Initial admin setup", "active")
    return {
        "status": "active",
        "access_token": create_access_token(user.id, session.id),
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "user": _user_payload(user),
    }


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request):
    if is_setup_required():
        raise HTTPException(status_code=409, detail="ابتدا نصب اولیه را کامل کنید.")
    manager = AuthManager()
    if not manager.validate(payload.username, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نام کاربری یا رمز عبور نادرست است، یا حساب غیرفعال شده است.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = manager.user
    session_status = "pending" if user.requires_session_activation else "active"
    session = _new_session(user, request, payload.client_name, session_status)
    if session_status == "pending":
        return {
            "status": "pending_activation",
            "session_ticket": create_activation_ticket(user.id, session.id),
            "expires_in": TOKEN_TTL_SECONDS,
            "message": "ورود ثبت شد؛ برای فعال‌سازی این نشست باید مدیر تأیید کند.",
        }
    return {
        "status": "active",
        "access_token": create_access_token(user.id, session.id),
        "expires_in": TOKEN_TTL_SECONDS,
        "user": _user_payload(user),
    }


@router.post("/auth/session-status")
def session_status(payload: SessionStatusRequest):
    ticket_payload = decode_activation_ticket(payload.ticket)
    try:
        user_id = UUID(ticket_payload["sub"])
        session_id = UUID(ticket_payload["sid"])
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="درخواست فعال‌سازی معتبر نیست.") from exc

    with DBManager():
        session = ApiSession.get_or_none(
            (ApiSession.id == session_id)
            & (ApiSession.user == user_id)
        )
        user = User.get_or_none(User.id == user_id)
        if session is None or user is None:
            raise HTTPException(status_code=401, detail="نشست دیگر وجود ندارد.")
        if not user.is_active:
            return {"status": "account_disabled", "message": "حساب توسط مدیر غیرفعال شده است."}
        if session.expires_at <= datetime.now() or session.status in ("revoked", "expired"):
            return {"status": "revoked", "message": "درخواست ورود منقضی یا لغو شده است."}
        if session.status == "pending":
            return {"status": "pending_activation", "message": "در انتظار تأیید مدیر هستید."}
        if session.status != "active":
            return {"status": "revoked", "message": "وضعیت نشست قابل استفاده نیست."}
        token = create_access_token(user.id, session.id)
        return {
            "status": "active",
            "access_token": token,
            "token_type": "bearer",
            "expires_in": TOKEN_TTL_SECONDS,
            "user": _user_payload(user),
        }


@router.get("/auth/me")
def current_identity(user=Depends(get_current_user)):
    return _user_payload(user)


@router.post("/auth/logout")
def logout(session=Depends(get_current_session)):
    now = datetime.now()
    with DBManager():
        current = ApiSession.get_or_none(ApiSession.id == session.id)
        if current is not None and current.status == "active":
            current.status = "revoked"
            current.revoked_at = now
            current.revocation_reason = "user_logout"
            current.save(only=[
                ApiSession.status, ApiSession.revoked_at,
                ApiSession.revocation_reason, ApiSession.updated_at,
            ])
    return {"status": "logged_out"}
