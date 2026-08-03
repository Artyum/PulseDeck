from __future__ import annotations

import os
from datetime import datetime, timezone

# Must set before importing app — override any inherited env vars (e.g. from .env.dev)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["STORAGE_SECRET"] = "test-secret"
os.environ["ENVIRONMENT"] = "dev"
os.environ["APP_BASE_URL"] = "http://testserver"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ.pop("ADMIN_EMAIL", None)
os.environ.pop("ADMIN_PASSWORD", None)
os.environ["SECURITY_CSRF_ENABLED"] = "false"
os.environ["AUTH_LOGIN_RATE_LIMIT"] = "100/minute"
os.environ["AUTH_FORGOT_PASSWORD_RATE_LIMIT"] = "100/minute"
os.environ["AUTH_ACTIVATE_RATE_LIMIT"] = "100/minute"
os.environ["AUTH_ADMIN_USER_CREATE_RATE_LIMIT"] = "100/minute"
os.environ["UPLOAD_RATE_LIMIT"] = "100/minute"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.session as db_session_module
import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import build_fastapi_app
from app.models.enums import UserRole
from app.models.user import User
from app.services import projects as project_service
from app.services.auth import set_password
from app.services.portal_settings import ensure_portal_settings_seed, invalidate_cache


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    previous_engine = db_session_module.engine
    previous_factory = db_session_module.SessionLocal
    db_session_module.engine = engine
    db_session_module.SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )

    seed_db = db_session_module.SessionLocal()
    try:
        ensure_portal_settings_seed(seed_db)
    finally:
        seed_db.close()
    invalidate_cache()

    yield engine

    invalidate_cache()
    db_session_module.engine = previous_engine
    db_session_module.SessionLocal = previous_factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        ensure_portal_settings_seed(session)
        invalidate_cache()
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_engine, db_session):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def _get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    from app.config import get_settings

    get_settings.cache_clear()
    invalidate_cache()
    app = build_fastapi_app()
    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db_session):
    user = User(
        email="admin@test.local",
        first_name="Admin",
        last_name="Test",
        role=UserRole.ADMIN,
        activated_at=datetime.now(timezone.utc),
    )
    set_password(user, "Admin123!abcd")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def client_user(db_session):
    user = User(
        email="client@test.local",
        first_name="Klient",
        last_name="Test",
        role=UserRole.USER,
        activated_at=datetime.now(timezone.utc),
    )
    set_password(user, "Client123!ab")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def staff_user(db_session):
    user = User(
        email="staff@test.local",
        first_name="Staff",
        last_name="Test",
        role=UserRole.STAFF,
        activated_at=datetime.now(timezone.utc),
    )
    set_password(user, "Staff123!abcd")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def project_with_members(db_session, client_user, staff_user):
    project = project_service.create_project(db_session, "Demo", "DEMO", "Opis")
    project_service.add_project_member(db_session, project.id, client_user.id)
    project_service.add_project_member(db_session, project.id, staff_user.id)
    return project
