"""Zależności autoryzacyjne — sesja użytkownika."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.middleware.session_sliding import SESSION_ACTIVITY_KEY
from app.models.enums import UserRole
from app.models.user import User
from app.utils.i18n import resolve_lang, t

SESSION_USER_ID_KEY = "user_id"
SESSION_AUTH_EPOCH_KEY = "auth_epoch"
SESSION_LAST_PROJECT_KEY = "last_project_key"

DbSession = Annotated[Session, Depends(get_db)]


def set_user_session(request: Request, user: User) -> None:
    request.session[SESSION_USER_ID_KEY] = str(user.id)
    request.session[SESSION_AUTH_EPOCH_KEY] = int(user.auth_epoch or 0)
    request.session[SESSION_ACTIVITY_KEY] = int(time.time())


def clear_user_session(request: Request) -> None:
    request.session.clear()


def set_last_project_key(request: Request, key: str) -> None:
    clean = (key or "").strip().upper()
    if clean:
        request.session[SESSION_LAST_PROJECT_KEY] = clean


def get_last_project_key(request: Request) -> str | None:
    raw = request.session.get(SESSION_LAST_PROJECT_KEY)
    if not raw:
        return None
    clean = str(raw).strip().upper()
    return clean or None


def get_optional_user_id(request: Request) -> int | None:
    raw = request.session.get(SESSION_USER_ID_KEY)
    if not raw:
        return None
    try:
        return int(str(raw))
    except (ValueError, TypeError):
        return None


def get_optional_user(request: Request, db: DbSession) -> User | None:
    user_id = get_optional_user_id(request)
    if not user_id:
        return None
    user = db.get(User, user_id)
    if not user:
        clear_user_session(request)
        return None
    if not user.is_active:
        clear_user_session(request)
        return None
    if user.activated_at is None:
        clear_user_session(request)
        return None
    session_epoch = request.session.get(SESSION_AUTH_EPOCH_KEY)
    try:
        session_epoch_int = int(session_epoch) if session_epoch is not None else 0
    except (TypeError, ValueError):
        session_epoch_int = -1
    if session_epoch_int != int(user.auth_epoch or 0):
        clear_user_session(request)
        return None
    return user


def require_user(request: Request, db: DbSession) -> User:
    user = get_optional_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=t(resolve_lang(request), "messages.http.login_required"),
        )
    return user


def require_admin(
    request: Request, user: Annotated[User, Depends(require_user)]
) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=t(resolve_lang(request), "messages.http.admin_required"),
        )
    return user


CurrentUser = Annotated[User, Depends(require_user)]
AdminUser = Annotated[User, Depends(require_admin)]
