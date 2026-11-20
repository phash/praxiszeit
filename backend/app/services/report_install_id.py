"""Persistente Installations-ID für Problemmeldungen (mrd-report-1, #557).

Liegt als ``system_settings``-Eintrag unter dem Default-Tenant (wie die
Backup-Einstellungen) und überlebt damit Updates (nativ und Docker).
"""
import logging
import uuid
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal, set_superadmin_context
from app.models.system_setting import SystemSetting
from app.services.backup_service import DEFAULT_TENANT_ID

logger = logging.getLogger(__name__)

INSTALL_ID_SETTING_KEY = "report_install_id"

# #557 D5: zuletzt gelesene/gespeicherte (oder ersatzweise erzeugte) ID dieses
# Prozesses. Scheitert die Datenbank, tragen Vorschau und Senden trotzdem
# dieselbe ID; ist sie lesbar, gilt immer der gespeicherte Wert.
_process_id: str | None = None


def _remember(value: str) -> str:
    global _process_id
    _process_id = value
    return value


def _valid(value: object) -> bool:
    try:
        return isinstance(value, str) and uuid.UUID(value).version == 4 and value == value.lower()
    except (ValueError, AttributeError):
        return False


def _read(db: Session) -> SystemSetting | None:
    # Superadmin-Kontext hebelt RLS aus -> Tenant-Filter ist Pflicht.
    return (
        db.query(SystemSetting)
        .filter(
            SystemSetting.key == INSTALL_ID_SETTING_KEY,
            SystemSetting.tenant_id == DEFAULT_TENANT_ID,
        )
        .first()
    )


def get_or_create_install_id(session_factory: Callable[[], Session] = SessionLocal) -> str:
    """Liefert die Installations-ID (UUIDv4, klein); wirft nie."""
    db = None
    try:
        db = session_factory()
        set_superadmin_context(db)
        row = _read(db)
        if row is not None and _valid(row.value):
            return _remember(row.value)
        new_id = str(uuid.uuid4())
        if row is not None:
            row.value = new_id
        else:
            db.add(SystemSetting(key=INSTALL_ID_SETTING_KEY, value=new_id, tenant_id=DEFAULT_TENANT_ID))
        try:
            db.commit()
            return _remember(new_id)
        except IntegrityError:
            db.rollback()
            set_superadmin_context(db)
            row = _read(db)
            if row is not None and _valid(row.value):
                return _remember(row.value)
            raise
    except Exception as exc:  # noqa: BLE001 - Meldung darf nie an der ID scheitern
        logger.warning("report install_id unavailable (%s)", type(exc).__name__)
        return _process_id or _remember(str(uuid.uuid4()))
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:  # noqa: BLE001
                pass
