from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from app.database import get_db
from app.models import User
from app.middleware.auth import require_admin
from app.services import error_log_service

router = APIRouter(prefix="/api/admin/errors", tags=["admin-errors"], dependencies=[Depends(require_admin)])


class ErrorLogResponse(BaseModel):
    id: str
    level: str
    logger: str
    message: str
    traceback: Optional[str] = None
    path: Optional[str] = None
    method: Optional[str] = None
    status_code: Optional[int] = None
    count: int
    first_seen: datetime
    last_seen: datetime
    status: str
    github_issue_url: Optional[str] = None

    @field_validator('traceback', mode='before')
    @classmethod
    def truncate_traceback(cls, v):
        if v and len(v) > 8000:
            return v[:8000] + '\n... [truncated]'
        return v

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_custom(cls, obj):
        return cls(
            id=str(obj.id),
            level=obj.level,
            logger=obj.logger,
            message=obj.message,
            traceback=obj.traceback,
            path=obj.path,
            method=obj.method,
            status_code=obj.status_code,
            count=obj.count,
            first_seen=obj.first_seen,
            last_seen=obj.last_seen,
            status=obj.status,
            github_issue_url=obj.github_issue_url,
        )


class UpdateStatusRequest(BaseModel):
    status: str  # 'open', 'ignored', 'resolved'


class SetGithubUrlRequest(BaseModel):
    github_issue_url: str = Field(..., pattern=r'^https://github\.com/[^/]+/[^/]+/issues/\d+$')


@router.get("/", response_model=List[ErrorLogResponse])
def list_errors(
    status: Optional[str] = Query(None, description="Filter by status: open, ignored, resolved"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all error log entries (admin only)."""
    errors = error_log_service.get_errors(db, status=status, limit=limit)
    return [ErrorLogResponse.from_orm_custom(e) for e in errors]


@router.patch("/{error_id}/status", response_model=ErrorLogResponse)
def update_error_status(
    error_id: str,
    body: UpdateStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update status of an error (open/ignored/resolved)."""
    if body.status not in ('open', 'ignored', 'resolved'):
        raise HTTPException(status_code=400, detail="Ungültiger Status")
    entry = error_log_service.update_status(db, error_id, body.status, str(current_user.id))
    if not entry:
        raise HTTPException(status_code=404, detail="Fehler nicht gefunden")
    return ErrorLogResponse.from_orm_custom(entry)


@router.delete("/{error_id}", status_code=204)
def delete_error(
    error_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Permanently delete an error log entry."""
    if not error_log_service.delete_error(db, error_id):
        raise HTTPException(status_code=404, detail="Fehler nicht gefunden")


@router.patch("/{error_id}/github-url", response_model=ErrorLogResponse)
def set_github_url(
    error_id: str,
    body: SetGithubUrlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Associate a GitHub issue URL with an error."""
    entry = error_log_service.set_github_url(db, error_id, body.github_issue_url)
    if not entry:
        raise HTTPException(status_code=404, detail="Fehler nicht gefunden")
    return ErrorLogResponse.from_orm_custom(entry)


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get error summary counts by status."""
    from sqlalchemy import func
    from app.models import ErrorLog
    counts = db.query(ErrorLog.status, func.count(ErrorLog.id)).group_by(ErrorLog.status).all()
    return {status: count for status, count in counts}
