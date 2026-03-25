from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from app.config import settings

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base for models
Base = declarative_base()


@event.listens_for(SessionLocal, "after_begin")
def _restore_tenant_context(session, transaction, connection):
    """Re-apply tenant context after every transaction begin (including after commit).

    SET LOCAL is transaction-scoped, so it's lost after db.commit(). This listener
    ensures the tenant_id (and superadmin flag) are re-set on every new transaction.
    """
    tenant_id = getattr(session, "_tenant_id", None)
    is_superadmin = getattr(session, "_is_superadmin", False)
    if tenant_id:
        connection.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_id)})
    if is_superadmin:
        connection.execute(text("SET LOCAL app.is_superadmin = 'true'"))


def set_tenant_context(db, tenant_id: str):
    """Set tenant context on a session. Persists across commits via event listener."""
    db._tenant_id = str(tenant_id)
    # Also set immediately for the current transaction
    db.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_id)})


def set_superadmin_context(db):
    """Grant superadmin access (bypasses RLS). Persists across commits via event listener."""
    db._is_superadmin = True
    db.execute(text("SET LOCAL app.is_superadmin = 'true'"))


def get_db():
    """Dependency for FastAPI to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db._tenant_id = None  # Clear tenant context
        db._is_superadmin = False  # Clear superadmin flag
        db.close()
