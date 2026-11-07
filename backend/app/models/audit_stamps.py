"""#537 (Audit 2026-11-07, A2-3): Rohstempel ins Aenderungsprotokoll.

``time_entry_audit_logs`` speicherte nur die ANGERECHNETEN Zeiten. Die
tatsaechlichen Stempel (``raw_start_time``/``raw_end_time``) standen allein auf
der ``time_entries``-Zeile — nach dem Loeschen eines Eintrags war die
tatsaechliche Arbeitszeit nirgends mehr belegt (§ 16 Abs. 2 ArbZG, EuGH
C-55/18: aufzuzeichnen ist die Arbeitszeit, nicht die bezahlte Zeit).

Statt die ~40 Stellen, die Protokollzeilen bauen, einzeln anzupassen (und die
Aufrufsignaturen von ``_create_audit_log`` & Co. zu aendern), fuellt dieser
Listener die Stempelspalten zentral beim Flush:

* ``new_*`` = aktueller Stand des Zeiteintrags (nur wenn die Zeile einen
  Nachher-Stand traegt, also nicht bei Loeschungen),
* ``old_*`` = Stand des Eintrags beim ersten Laden in DIESER Transaktion (bzw.
  der zuletzt protokollierte Nachher-Stand, falls dieselbe Transaktion den
  Eintrag mehrfach protokolliert). Ohne Laden (neu angelegter Eintrag) gibt es
  keinen Vorher-Stand.

Werte, die eine Schreibstelle selbst setzt, gewinnen. Protokollzeilen ohne
``time_entry_id`` (Abwesenheiten, Einstellungen, Sammelzeilen) bleiben
unberuehrt.
"""
import uuid
from types import SimpleNamespace

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.util import identity_key

from app.models.time_entry import TimeEntry
from app.models.time_entry_audit_log import TimeEntryAuditLog

_STATE = "pz_audit_entry_state"   # {entry_id: SimpleNamespace} — Vorher-Stand
_DIRTY = "pz_audit_entry_dirty"   # Eintraege, die diese Transaktion schon schrieb
_FIELDS = ("start_time", "end_time", "raw_start_time", "raw_end_time",
           "uncredited_minutes", "auto_closed")


def _snapshot(values) -> SimpleNamespace:
    return SimpleNamespace(**{f: values.get(f) for f in _FIELDS})


def _stamp_values(snap) -> dict:
    """Die vier Protokollwerte aus einem Stand — Ende der Anwesenheit ueber DIE
    eine Regel ``work_window_service.presence_end`` (auto_closed → wirksames
    Ende, nie das synthetische 23:59)."""
    from app.services.work_window_service import presence_end

    return {
        "raw_start_time": snap.raw_start_time,
        "raw_end_time": snap.raw_end_time,
        "presence_end_time": presence_end(snap),
        "uncredited_minutes": snap.uncredited_minutes,
    }


def _loaded_values(target) -> dict | None:
    d = target.__dict__
    if not all(f in d for f in _FIELDS):
        return None  # Teil-Refresh: Stand unvollstaendig, nichts festhalten
    return {f: d[f] for f in _FIELDS}


def _remember_loaded(target, session) -> None:
    if session is None or target.id is None:
        return
    if target.id in session.info.get(_DIRTY, ()):
        return  # schon geschrieben: ein Neuladen ist nicht mehr der Vorher-Stand
    values = _loaded_values(target)
    if values is not None:
        session.info.setdefault(_STATE, {}).setdefault(target.id, _snapshot(values))


@event.listens_for(TimeEntry, "load")
def _on_entry_load(target, context):
    _remember_loaded(target, context.session)


@event.listens_for(TimeEntry, "refresh")
def _on_entry_refresh(target, context, attrs):
    _remember_loaded(target, context.session)


def _committed_values(entry) -> dict:
    committed = inspect(entry).committed_state
    return {f: committed.get(f, getattr(entry, f, None)) for f in _FIELDS}


def _find_entry(session, entry_id):
    obj = session.identity_map.get(identity_key(TimeEntry, entry_id))
    if obj is not None:
        return obj
    for pending in session.new:
        if isinstance(pending, TimeEntry) and pending.id == entry_id:
            return pending
    return None


def _has_side(log, side: str) -> bool:
    return any(getattr(log, f"{side}_{f}") is not None for f in ("date", "start_time", "end_time"))


def _apply(log, side: str, values: dict) -> None:
    for name, value in values.items():
        attr = f"{side}_{name}"
        if getattr(log, attr) is None:
            setattr(log, attr, value)


def _fill(session, log) -> None:
    entry_id = log.time_entry_id or log.entry_ref
    if entry_id is None:
        return
    if not isinstance(entry_id, uuid.UUID):
        try:
            entry_id = uuid.UUID(str(entry_id))
        except ValueError:
            return
    entry = _find_entry(session, entry_id)
    state = session.info.setdefault(_STATE, {})

    if _has_side(log, "old"):
        snap = state.get(entry_id)
        if snap is None and entry is not None and entry not in session.new:
            snap = _snapshot(_committed_values(entry))
        if snap is not None:
            _apply(log, "old", _stamp_values(snap))

    if _has_side(log, "new") and entry is not None and entry not in session.deleted:
        current = _snapshot({f: getattr(entry, f, None) for f in _FIELDS})
        _apply(log, "new", _stamp_values(current))
        # Naechste Protokollzeile desselben Eintrags in dieser Transaktion:
        # ihr Vorher ist dieses Nachher.
        state[entry_id] = current


@event.listens_for(Session, "before_flush")
def _fill_audit_stamps(session, flush_context, instances):
    for obj in list(session.new):
        if isinstance(obj, TimeEntryAuditLog):
            _fill(session, obj)


@event.listens_for(Session, "after_flush")
def _mark_written_entries(session, flush_context):
    dirty = session.info.setdefault(_DIRTY, set())
    for obj in list(session.dirty) + list(session.new) + list(session.deleted):
        if isinstance(obj, TimeEntry) and obj.id is not None:
            dirty.add(obj.id)


@event.listens_for(Session, "after_transaction_end")
def _forget_state(session, transaction):
    if transaction.parent is None:
        session.info.pop(_STATE, None)
        session.info.pop(_DIRTY, None)
