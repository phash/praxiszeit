"""#537 (Audit 2026-11-07, A2-3): Rohstempel ins Aenderungsprotokoll.

``time_entry_audit_logs`` speicherte nur die ANGERECHNETEN Zeiten. Die
tatsaechlichen Stempel (``raw_start_time``/``raw_end_time``) standen allein auf
der ``time_entries``-Zeile — nach dem Loeschen eines Eintrags war die
tatsaechliche Arbeitszeit nirgends mehr belegt (§ 16 Abs. 2 ArbZG, EuGH
C-55/18: aufzuzeichnen ist die Arbeitszeit, nicht die bezahlte Zeit).

Statt die ~40 Stellen, die Protokollzeilen bauen, einzeln anzupassen (und die
Aufrufsignaturen von ``_create_audit_log`` & Co. zu aendern), haelt dieser
Listener den Stand beim Hinzufuegen der Protokollzeile (``session.add``) fest
und fuellt die Stempelspalten beim Flush (in Reihenfolge des Hinzufuegens):

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


_SNAP_ATTR = "_pz_stamp_snap"   # am Protokollobjekt: (Vorher-Stand, Nachher-Stand)
_ORDER = "pz_audit_add_order"    # Zaehler: Reihenfolge des Hinzufuegens


def _entry_id_of(log):
    entry_id = log.time_entry_id or log.entry_ref
    if entry_id is None:
        return None
    if not isinstance(entry_id, uuid.UUID):
        try:
            entry_id = uuid.UUID(str(entry_id))
        except ValueError:
            return None
    return entry_id


def _take_snapshot(session, log) -> bool:
    """Haelt Vorher-/Nachher-Stand des Eintrags fest — zum Zeitpunkt, an dem die
    Protokollzeile gebaut wird (``session.add``), nicht erst beim Flush: in
    einem Flush mit zwei Zeilen zum selben Eintrag (XLS-Import mit doppelter
    Dateizeile, Zeile vor weiteren Aenderungen) traegt sonst jede den Endstand
    (Review-Runde 2026-11-07). False = Eintrag (noch) nicht greifbar."""
    entry_id = _entry_id_of(log)
    if entry_id is None:
        return False
    entry = _find_entry(session, entry_id)
    state = session.info.setdefault(_STATE, {})
    old = state.get(entry_id)
    if old is None and entry is not None and entry not in session.new:
        old = _snapshot(_committed_values(entry))
    new = None
    if entry is not None and entry not in session.deleted:
        new = _snapshot({f: getattr(entry, f, None) for f in _FIELDS})
    if old is None and new is None:
        return False
    setattr(log, _SNAP_ATTR, (old, new))
    if new is not None and _has_side(log, "new"):
        # Naechste Protokollzeile desselben Eintrags: ihr Vorher ist dieses Nachher.
        state[entry_id] = new
    return True


def _fill(session, log) -> None:
    snaps = getattr(log, _SNAP_ATTR, None)
    if snaps is None:
        # Ohne Stand beim Hinzufuegen (Eintrag noch ohne id): jetzt festhalten.
        if not _take_snapshot(session, log):
            return
        snaps = getattr(log, _SNAP_ATTR)
    old, new = snaps
    if old is not None and _has_side(log, "old"):
        _apply(log, "old", _stamp_values(old))
    if new is not None and _has_side(log, "new"):
        _apply(log, "new", _stamp_values(new))


@event.listens_for(Session, "transient_to_pending")
def _on_audit_added(session, instance):
    if isinstance(instance, TimeEntryAuditLog):
        order = session.info.get(_ORDER, 0) + 1
        session.info[_ORDER] = order
        instance._pz_add_order = order
        _take_snapshot(session, instance)


@event.listens_for(Session, "before_flush")
def _fill_audit_stamps(session, flush_context, instances):
    logs = [o for o in session.new if isinstance(o, TimeEntryAuditLog)]
    logs.sort(key=lambda o: getattr(o, "_pz_add_order", 0))
    for obj in logs:
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
        session.info.pop(_ORDER, None)
