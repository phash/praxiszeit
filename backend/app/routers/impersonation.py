"""Read-only Impersonation ("Login als …", #370).

An admin may view the app from an employee's perspective (dashboard, calendar,
etc.) to reproduce reports or test the UI. The session is **strictly read-only**
(``ImpersonationReadOnlyMiddleware`` blocks every write) so no action can ever be
falsely attributed to the employee — the legal core of #370 (§16 ArbZG /
Willenserklärungen). Each session is logged in ``impersonation_sessions`` for
DSGVO Art. 5(2) accountability.

Two endpoints:
* ``POST /api/admin/users/{user_id}/impersonate`` (admin only) — start a session,
  returns a read-only impersonation access token (``imp`` claim = the admin).
* ``POST /api/admin/impersonate/end`` — end the current session. Callable *with
  the impersonation token* (the effective role is ``employee``, so it must NOT be
  admin-gated); whitelisted in the read-only middleware.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.models import User, UserRole, ImpersonationSession
from app.middleware.auth import get_current_user, require_admin
from app.schemas.user import UserListResponse
from app.services import auth_service
from app.services.timezone_service import now_local

router = APIRouter(prefix="/api/admin", tags=["impersonation"])


def _decode_bearer(request: Request) -> dict | None:
    """Decode the request's bearer token (already authenticated upstream)."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    return auth_service.decode_token(auth.split(" ", 1)[1])


@router.post("/users/{user_id}/impersonate")
def start_impersonation(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Start a read-only impersonation session for an employee.

    Only non-admin users of the caller's own tenant can be impersonated.
    """
    target = (
        db.query(User)
        .filter(User.id == user_id, User.tenant_id == current_user.tenant_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Sie können sich nicht selbst impersonieren.")
    if target.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Administrator:innen können nicht impersoniert werden — nur Mitarbeiter:innen.",
        )
    if not target.is_active:
        raise HTTPException(status_code=400, detail="Benutzer ist deaktiviert.")

    session = ImpersonationSession(
        tenant_id=current_user.tenant_id,
        impersonator_id=current_user.id,
        target_id=target.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    tenant_id_str = str(current_user.tenant_id) if current_user.tenant_id else None
    token = auth_service.create_access_token(
        user_id=str(target.id),
        role=target.role.value,
        token_version=target.token_version,
        tenant_id=tenant_id_str,
        impersonator_id=str(current_user.id),
        impersonation_session_id=str(session.id),
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserListResponse.model_validate(target),
    }


@router.get("/impersonation-sessions")
def list_impersonation_sessions(
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """#370: the DSGVO Art. 5(2) accountability log — who viewed the app as whom,
    and when. Admin-only, tenant-scoped (RLS + F-026), most recent first."""
    limit = max(1, min(limit, 500))
    imp = aliased(User)
    tgt = aliased(User)
    rows = (
        db.query(ImpersonationSession, imp, tgt)
        .join(imp, ImpersonationSession.impersonator_id == imp.id)
        .join(tgt, ImpersonationSession.target_id == tgt.id)
        .filter(ImpersonationSession.tenant_id == current_user.tenant_id)
        .order_by(ImpersonationSession.started_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(s.id),
            "impersonator_name": f"{a.first_name} {a.last_name}".strip() or a.username,
            "target_name": f"{t.first_name} {t.last_name}".strip() or t.username,
            "started_at": s.started_at,
            "ended_at": s.ended_at,
        }
        for s, a, t in rows
    ]


@router.post("/impersonate/end")
def end_impersonation(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """End the active impersonation session (idempotent).

    Must be reachable *with the impersonation token* (effective role = employee),
    so it is only ``get_current_user``-gated and whitelisted in the read-only
    middleware. The session id is the token's ``imp_sid`` claim; the token is
    already authenticated by ``get_current_user``.
    """
    payload = _decode_bearer(request) or {}
    sid = payload.get("imp_sid")
    if not sid:
        raise HTTPException(status_code=400, detail="Keine aktive Impersonation-Session.")

    session = (
        db.query(ImpersonationSession)
        .filter(
            ImpersonationSession.id == sid,
            ImpersonationSession.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if session and session.ended_at is None:
        session.ended_at = now_local()
        db.commit()
    return {"message": "Impersonation beendet."}
