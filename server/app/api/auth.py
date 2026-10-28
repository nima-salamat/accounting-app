"""Public setup/login endpoints and authenticated identity lookup."""
import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status

from accounting_app.services.authentication import AuthManager
from accounting_app.services.installer import complete_initial_setup, is_setup_required
from server.app.config import TOKEN_TTL_SECONDS
from server.app.dependencies import get_current_user
from server.app.schemas import LoginRequest, SetupRequest, TokenResponse
from server.app.security import create_access_token

router = APIRouter(tags=["authentication"])


def _user_payload(user):
    return {
        "id": str(user.id),
        "username": user.username,
        "is_admin": bool(user.is_admin),
        "buttons": user.buttons,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


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
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "user": _user_payload(user),
    }


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    if is_setup_required():
        raise HTTPException(status_code=409, detail="ابتدا نصب اولیه را کامل کنید.")
    manager = AuthManager()
    if not manager.validate(payload.username, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نام کاربری یا رمز عبور نادرست است.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "access_token": create_access_token(manager.user.id),
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
    }


@router.get("/auth/me")
def current_identity(user=Depends(get_current_user)):
    return _user_payload(user)
