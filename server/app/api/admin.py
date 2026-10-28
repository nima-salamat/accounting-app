"""Administrative user/session lifecycle endpoints."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from accounting_app.database.connection import DBManager
from accounting_app.database.models import ApiSession, User
from server.app.dependencies import require_admin
from server.app.schemas import SessionRevokeRequest

router = APIRouter(prefix="/admin", tags=["administration"])


def _session_payload(session, user):
    return {
        "id": str(session.id),
        "user_id": str(user.id),
        "username": user.username,
        "is_admin": bool(user.is_admin),
        "is_active": bool(user.is_active),
        "requires_session_activation": bool(user.requires_session_activation),
        "status": session.status,
        "client_name": session.client_name,
        "remote_addr": session.remote_addr,
        "user_agent": session.user_agent,
        "created_at": session.created_at,
        "last_seen_at": session.last_seen_at,
        "expires_at": session.expires_at,
        "activated_at": session.activated_at,
        "revoked_at": session.revoked_at,
        "revocation_reason": session.revocation_reason,
    }


@router.get("/overview")
def admin_overview(_admin=Depends(require_admin)):
    with DBManager():
        return {
            "users_total": User.select().count(),
            "users_active": User.select().where(User.is_active == True).count(),
            "users_disabled": User.select().where(User.is_active == False).count(),
            "sessions_pending": ApiSession.select().where(ApiSession.status == "pending").count(),
            "sessions_active": ApiSession.select().where(ApiSession.status == "active").count(),
            "sessions_revoked": ApiSession.select().where(ApiSession.status == "revoked").count(),
        }


@router.get("/sessions")
def list_sessions(
    state: str = Query("all", pattern="^(all|pending|active|revoked|expired)$"),
    q: Optional[str] = Query(default=None, max_length=256),
    limit: int = Query(200, ge=1, le=500),
    _admin=Depends(require_admin),
):
    with DBManager():
        query = ApiSession.select().join(User).order_by(
            ApiSession.status, ApiSession.created_at.desc()
        )
        if state != "all":
            query = query.where(ApiSession.status == state)
        if q and q.strip():
            query = query.where(User.username.contains(q.strip()))
        result = []
        for session in query.limit(limit):
            user = session.user
            result.append(_session_payload(session, user))
        return result


@router.post("/sessions/{session_id}/activate")
def activate_session(session_id: UUID, admin=Depends(require_admin)):
    now = datetime.now()
    with DBManager():
        session = ApiSession.get_or_none(ApiSession.id == session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="نشست پیدا نشد.")
        if session.status != "pending":
            raise HTTPException(status_code=409, detail="این نشست دیگر در انتظار فعال‌سازی نیست.")
        if session.expires_at <= now:
            session.status = "expired"
            session.revoked_at = now
            session.revocation_reason = "activation_expired"
            session.save()
            raise HTTPException(status_code=409, detail="مهلت این درخواست ورود به پایان رسیده است.")
        user = User.get_or_none(User.id == session.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=409, detail="حساب کاربری غیرفعال است.")
        session.status = "active"
        session.activated_at = now
        session.last_seen_at = now
        session.save()
        return _session_payload(session, user)


@router.post("/sessions/{session_id}/revoke", status_code=status.HTTP_200_OK)
def revoke_session(
    session_id: UUID,
    payload: SessionRevokeRequest = SessionRevokeRequest(),
    _admin=Depends(require_admin),
):
    now = datetime.now()
    with DBManager():
        session = ApiSession.get_or_none(ApiSession.id == session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="نشست پیدا نشد.")
        if session.status not in ("pending", "active"):
            raise HTTPException(status_code=409, detail="این نشست قبلاً خاتمه یافته است.")
        session.status = "revoked"
        session.revoked_at = now
        session.revocation_reason = payload.reason or "revoked_by_admin"
        session.save()
        user = User.get_or_none(User.id == session.user_id)
        return _session_payload(session, user)


@router.post("/sessions/revoke-all")
def revoke_all_sessions(_admin=Depends(require_admin)):
    now = datetime.now()
    with DBManager():
        count = ApiSession.update(
            status="revoked", revoked_at=now,
            revocation_reason="revoked_all_by_admin",
        ).where(ApiSession.status.in_(("pending", "active"))).execute()
    return {"revoked_count": int(count)}
