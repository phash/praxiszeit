"""#537 (Audit 2026-11-07, A2-1/A2-2/A2-8/A2-12): Kette, Pruefung und die drei
erlaubten Aenderungen am Aenderungsprotokoll.

Seit Migration 076 darf die App-Rolle ``time_entry_audit_logs`` nur noch
anfuegen (Trigger ``pz_audit_guard`` + entzogene Rechte). Was die Anwendung
an bestehenden Zeilen noch aendern muss, laeuft ausschliesslich hier durch:

* ``seal_chain`` — versiegelt die noch losen Zeilen eines Mandanten zur Kette
  (``chain_seq``/``chain_prev``/``chain_hash``) ueber ``pz_audit_seal``.
* ``set_notes`` — Art.-17-Scrub der Notizen (Anonymisierung) ueber
  ``pz_audit_set_notes``; die Pruefsumme wird nur neu berechnet, wenn die Zeile
  vorher stimmte (eine manipulierte Zeile wird nicht reingewaschen).
* ``delete_rows`` — Loeschen VERSIEGELTER Zeilen (Endloeschung nach Art. 17,
  Aufbewahrungsfrist) ueber ``pz_audit_delete``; dazu eine gehashte
  Vermerk-Zeile, die die entfernten Kettenglieder nennt — so bleibt jede andere
  Luecke als Loeschung erkennbar.

Auf SQLite (Tests) gibt es weder Trigger noch Funktionen; dort aendern dieselben
Wege die Zeilen ueber die Objektschicht.

``verify_tenant`` prueft Inhalt (``row_hash``), Kette (Glieder, Luecken,
Kopf) und meldet Altbestand getrennt; ``run_daily_check`` versiegelt und prueft
taeglich jeden Mandanten und meldet Abweichungen (``security_events`` +
``error_logs``).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.core import audit_integrity
from app.models import SecurityEvent, SystemSetting, Tenant, TimeEntryAuditLog
from app.models.security_event import EVENT_AUDIT_CHAIN_REANCHORED, EVENT_AUDIT_INTEGRITY_FAILED  # noqa: F401

logger = logging.getLogger(__name__)

PURGE_ACTION = "audit_rows_purged"
HEAD_SETTING_KEY = "audit_chain_head"
LAST_CHECK_SETTING_KEY = "audit_integrity_last_check"
LEGACY_CUTOFF_KEY = "audit_legacy_cutoff"   # Migration 076: feste Grenze fuer Altbestand
REANCHOR_ACTION = "audit_chain_reanchored"   # < 40 Zeichen (varchar(40))
REANCHOR_SOURCE = "audit_reanchor"
_SEAL_BATCH = 500
_MARKER_RE = re.compile(r"Kettenglieder ([0-9,\-]+)")
# Aktionen, deren Zeilen an einem Zeiteintrag hingen (Altbestand, A2-1).
_ENTRY_ACTIONS = ("create", "update", "delete")


def _is_pg(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def chain_lock_key(tenant_id) -> int:
    digest = hashlib.blake2b(f"audit_chain:{tenant_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def _lock_chain(db: Session, tenant_id) -> None:
    """Ein Versiegler je Mandant (sonst zwei Ketten-Enden). Nie in try/except:
    ein gescheitertes Statement bricht die PG-Transaktion ab (CLAUDE.md 1.21.1)."""
    if _is_pg(db):
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": chain_lock_key(tenant_id)})


# ── Kettenkopf ──────────────────────────────────────────────────────────────
# Der Kopf (letztes Glied) steht gesiegelt in ``system_settings``: ohne ihn
# fiele das Abschneiden der letzten Glieder nicht auf (keine Luecke dahinter).
# Fehlt er oder stimmt er nicht, obwohl versiegelte Glieder existieren, wird er
# NIE stillschweigend neu angelegt — sonst loeschte der naechste Lauf den Befund
# (Review-Runde 2026-11-07). Versiegeln und Loeschen sind dann gesperrt, bis die
# Verwaltung das Kettenende bewusst neu setzt (``reanchor_chain``, mit Grund und
# gehashtem Vermerk). Auf PostgreSQL kann die App-Rolle die Kopfzeile zudem
# weder loeschen noch umbenennen (Trigger ``pz_audit_head_guard``, Migration 076).


class AuditChainBroken(Exception):
    """Kettenende fehlt oder ist ungueltig, obwohl versiegelte Glieder existieren."""

    def __init__(self, problem: str):
        self.problem = problem
        super().__init__(
            f"Das Änderungsprotokoll meldet eine Abweichung: Kettenende {problem}. "
            "Löschen und Versiegeln von Protokollzeilen sind gesperrt, bis die Abweichung "
            "geklärt ist — siehe Änderungsprotokoll → „Prüfung des Änderungsprotokolls“."
        )


def _head_mac(tenant_id, seq: int, chain_hash: str) -> str:
    return audit_integrity.compute_head_mac(tenant_id, seq, chain_hash)


def _read_head(db: Session, tenant_id):
    row = db.query(SystemSetting).filter(
        SystemSetting.key == HEAD_SETTING_KEY, SystemSetting.tenant_id == tenant_id,
    ).first()
    if row is None:
        return None
    try:
        seq_s, chain_hash, mac = (row.value or "").split(":")
        return int(seq_s), chain_hash, mac
    except ValueError:
        return (-1, "", "")  # zerstoert → Siegel passt nie


def _write_head(db: Session, tenant_id, seq: int, chain_hash: str, *, reanchor: bool = False) -> None:
    """Kettenende fortschreiben. Auf PostgreSQL nur ueber ``pz_audit_set_head``
    (die App-Rolle darf die Zeile nicht direkt schreiben, Migration 076): nur
    auf das hoechste versiegelte Glied, nie zurueck — ausser beim bewussten
    Neusetzen (``reanchor``) mit noch loser Vermerk-Zeile."""
    value = f"{seq}:{chain_hash}:{_head_mac(tenant_id, seq, chain_hash)}"
    row = db.query(SystemSetting).filter(
        SystemSetting.key == HEAD_SETTING_KEY, SystemSetting.tenant_id == tenant_id,
    ).first()
    if _is_pg(db):
        db.flush()
        db.execute(text("SELECT pz_audit_set_head(CAST(:t AS uuid), :v, :r)"),
                   {"t": str(tenant_id), "v": value, "r": reanchor})
        if row is not None:
            set_committed_value(row, "value", value)
        return
    if row is None:
        db.add(SystemSetting(key=HEAD_SETTING_KEY, tenant_id=tenant_id, value=value,
                             description="Änderungsprotokoll: letztes Kettenglied (#537)"))
    else:
        row.value = value


def _chain_top(db: Session, tenant_id) -> tuple:
    last = db.query(TimeEntryAuditLog.chain_seq, TimeEntryAuditLog.chain_hash).filter(
        TimeEntryAuditLog.tenant_id == tenant_id,  # F-026
        TimeEntryAuditLog.chain_seq.isnot(None),
    ).order_by(TimeEntryAuditLog.chain_seq.desc()).first()
    return (last.chain_seq, last.chain_hash or "") if last else (0, "")


def head_problem(db: Session, tenant_id, top: tuple | None = None) -> str | None:
    """``None`` = Kettenende in Ordnung (oder noch nichts versiegelt), sonst ein
    kurzer Befund. ``top`` = (hoechstes vorhandenes Glied, dessen Hash)."""
    top_seq, top_hash = top if top is not None else _chain_top(db, tenant_id)
    head = _read_head(db, tenant_id)
    if head is None:
        return "fehlt" if top_seq > 0 else None
    h_seq, h_hash, h_mac = head
    if h_seq < 0 or not hmac.compare_digest(h_mac or "", _head_mac(tenant_id, h_seq, h_hash)):
        return "ungültig (Siegel passt nicht)"
    if h_seq < top_seq:
        return f"zeigt auf Glied {h_seq}, vorhanden sind Glieder bis {top_seq}"
    if h_seq == top_seq and top_seq > 0 and h_hash != top_hash:
        return f"passt nicht zu Glied {top_seq}"
    return None


# ── Versiegeln ──────────────────────────────────────────────────────────────

def seal_chain(db: Session, tenant_id) -> int:
    """Versiegelt alle noch losen Zeilen des Mandanten (Reihenfolge: Anlage).
    Gibt die Zahl neu versiegelter Zeilen zurueck. Committet nicht.
    Wirft ``AuditChainBroken``, wenn das Kettenende nicht stimmt."""
    _lock_chain(db, tenant_id)
    db.flush()
    top = _chain_top(db, tenant_id)
    problem = head_problem(db, tenant_id, top)
    if problem is not None:
        raise AuditChainBroken(problem)
    seq, prev = top
    head = _read_head(db, tenant_id)
    if head is not None and head[0] > seq:
        seq, prev = head[0], head[1]  # letztes Glied legitim entfernt

    rows = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.tenant_id == tenant_id,  # F-026
        TimeEntryAuditLog.chain_seq.is_(None),
    ).order_by(TimeEntryAuditLog.created_at, TimeEntryAuditLog.id).all()
    if not rows:
        return 0

    pg = _is_pg(db)
    batch: list = []

    def _flush_batch():
        if pg and batch:
            db.execute(
                text("SELECT pz_audit_seal(CAST(:ids AS uuid[]), CAST(:seqs AS bigint[]), "
                     "CAST(:prevs AS text[]), CAST(:hashes AS text[]))"),
                {"ids": [str(r.id) for r, *_ in batch], "seqs": [s for _, s, _, _ in batch],
                 "prevs": [p for _, _, p, _ in batch], "hashes": [h for *_, h in batch]},
            )
        batch.clear()

    for row in rows:
        seq += 1
        chain_hash = audit_integrity.compute_chain_hash(tenant_id, seq, row.id, prev, row.hash_version)
        if pg:
            for attr, value in (("chain_seq", seq), ("chain_prev", prev), ("chain_hash", chain_hash)):
                set_committed_value(row, attr, value)
            batch.append((row, seq, prev, chain_hash))
            if len(batch) >= _SEAL_BATCH:
                _flush_batch()
        else:
            row.chain_seq, row.chain_prev, row.chain_hash = seq, prev, chain_hash
        prev = chain_hash
    _flush_batch()
    _write_head(db, tenant_id, seq, prev)
    db.flush()
    return len(rows)


# ── Notiz-Scrub (Art. 17) ───────────────────────────────────────────────────

def set_notes(db: Session, row: TimeEntryAuditLog, old_note, new_note) -> None:
    """Ersetzt die beiden Notizen einer Zeile. Die Pruefsumme wird nur dann neu
    berechnet, wenn die Zeile vorher stimmte — eine bereits manipulierte Zeile
    bleibt so als manipuliert erkennbar, eine ungehashte bleibt ungehasht."""
    was_valid = bool(row.row_hash) and audit_integrity.verify_row(row)
    if _is_pg(db):
        set_committed_value(row, "old_note", old_note)
        set_committed_value(row, "new_note", new_note)
        new_hash = audit_integrity.compute_row_hash(row) if was_valid else row.row_hash
        set_committed_value(row, "row_hash", new_hash)
        db.execute(
            text("SELECT pz_audit_set_notes(CAST(:id AS uuid), :o, :n, :h)"),
            {"id": str(row.id), "o": old_note, "n": new_note, "h": new_hash},
        )
    else:
        row.old_note = old_note
        row.new_note = new_note
        if was_valid:
            row.row_hash = audit_integrity.compute_row_hash(row)


# ── Loeschen (Art. 17, Aufbewahrungsfrist) ──────────────────────────────────

def _ranges(seqs) -> str:
    seqs = sorted(seqs)
    out, start, prev = [], None, None
    for s in seqs:
        if start is None:
            start = prev = s
        elif s == prev + 1:
            prev = s
        else:
            out.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = s
    if start is not None:
        out.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(out)


def parse_marker_seqs(note) -> set:
    found = set()
    m = _MARKER_RE.search(note or "")
    if not m:
        return found
    for part in m.group(1).split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit():
                found.update(range(int(a), int(b) + 1))
        elif part.isdigit():
            found.add(int(part))
    return found


def delete_rows(db: Session, rows, *, tenant_id, user_id, changed_by, source: str,
                reason: str) -> int:
    """Loescht Protokollzeilen legitim: erst versiegeln, dann ueber
    ``pz_audit_delete`` entfernen, dann eine gehashte Vermerk-Zeile anlegen, die
    die entfernten Kettenglieder nennt. ``user_id`` traegt die Vermerk-Zeile
    (betroffene Person bzw. der handelnde Verwalter); ``changed_by`` darf
    ``None`` sein (Systemlauf). Gibt die Zahl geloeschter Zeilen zurueck."""
    rows = [r for r in rows if r.tenant_id == tenant_id]  # F-026
    if not rows:
        return 0
    seal_chain(db, tenant_id)
    # Kettenglieder aus der DATENBANK lesen, nicht von den Objekten: hat eine
    # andere Sitzung (parallele Endloeschung, naechtliche Pruefung) die Zeilen
    # versiegelt, nachdem dieser Aufruf sie geladen hatte, tragen die Objekte
    # noch ``chain_seq = None`` und der Vermerk nennte kein Glied. Nach
    # ``_lock_chain`` in ``seal_chain`` ist der gelesene Stand verbindlich.
    ids = [r.id for r in rows]
    seq_by_id = dict(db.query(TimeEntryAuditLog.id, TimeEntryAuditLog.chain_seq).filter(
        TimeEntryAuditLog.tenant_id == tenant_id,  # F-026
        TimeEntryAuditLog.id.in_(ids),
    ).all())
    # Zeilen, die eine andere Sitzung inzwischen selbst entfernt hat, fehlen hier
    # und gehoeren nicht in diesen Vermerk.
    rows = [r for r in rows if r.id in seq_by_id]
    if not rows:
        return 0
    seqs = [seq_by_id[r.id] for r in rows]
    if any(s is None for s in seqs):  # seal_chain versiegelt unter der Sperre alles
        raise RuntimeError("Zu loeschende Protokollzeile ist nach dem Versiegeln noch lose")
    if _is_pg(db):
        deleted = db.execute(
            text("SELECT pz_audit_delete(CAST(:ids AS uuid[]))"),
            {"ids": [str(r.id) for r in rows]},
        ).scalar()
        for r in rows:
            db.expunge(r)
    else:
        for r in rows:
            db.delete(r)
        db.flush()
        deleted = len(rows)
    db.add(TimeEntryAuditLog(
        time_entry_id=None,
        user_id=user_id,
        changed_by=changed_by,
        action=PURGE_ACTION,
        source=source,
        new_note=f"Kettenglieder {_ranges(seqs)} entfernt ({deleted} Zeilen): {reason}",
        tenant_id=tenant_id,
    ))
    db.flush()
    return int(deleted or 0)


# ── Pruefung ────────────────────────────────────────────────────────────────

# Quellen, deren Zeilen eine Antrags-id tragen (Genehmigung eines
# Aenderungsantrags; ``admin_change_requests``).
_CR_SOURCES = ("change_request", "break_waiver", "credit_override")


def _is_legacy_entry_row(row) -> bool:
    """Altbestand (v2), dessen Verweis schon VOR Migration 076 genullt wurde
    (``ON DELETE SET NULL``): eine Kopie gab es nie, die Pruefsumme ist nicht
    nachrechenbar (A2-1) — aber auch kein Beleg fuer eine Manipulation.

    * Zeiteintrag geloescht: ``time_entry_id``/``entry_ref`` leer bei einer
      Eintragszeile mit Zeiten.
    * Aenderungsantrag geloescht: ``change_request_id``/``change_request_ref``
      leer bei einer Zeile aus einer Antragsgenehmigung (Review-Runde
      2026-11-07; vor dem Sperr-Fix in ``change_requests.withdraw`` konnte ein
      gerade genehmigter Antrag noch geloescht werden)."""
    if row.hash_version is not None:
        return False
    entry_gone = (
        row.time_entry_id is None and row.entry_ref is None
        and row.action in _ENTRY_ACTIONS
        and (row.old_start_time is not None or row.new_start_time is not None)
    )
    cr_gone = (
        row.change_request_id is None and row.change_request_ref is None
        and row.source in _CR_SOURCES
    )
    return entry_gone or cr_gone


_CUTOFF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}$")


def read_legacy_cutoff(db: Session, tenant_id) -> str | None:
    """Feste Grenze fuer Altbestand ohne Pruefsumme (``canonical_timestamp``),
    von Migration 076 je Mandant festgehalten — nie aus ``created_at``
    abgeleitet (Review-Runde 2). Die App-Rolle kann sie nicht schreiben
    (Trigger ``pz_audit_head_guard``). ``None`` = keine (gueltige) Grenze."""
    value = db.query(SystemSetting.value).filter(
        SystemSetting.key == LEGACY_CUTOFF_KEY, SystemSetting.tenant_id == tenant_id,
    ).scalar()
    return value if value and _CUTOFF_RE.match(value) else None


def verify_tenant(db: Session, tenant_id) -> dict:
    """Prueft das Protokoll eines Mandanten. ``intact`` = keine manipulierte Zeile,
    kein unerklaertes fehlendes Kettenglied, Kopf stimmt."""
    legacy_cutoff = read_legacy_cutoff(db, tenant_id)

    checked = ok = tampered = legacy = legacy_deleted = unsealed = reanchored = 0
    tampered_ids: list[str] = []
    legacy_deleted_ids: list[str] = []
    links: dict[int, tuple] = {}
    purged: set = set()
    seen_bad: set = set()

    def _bad(row):
        nonlocal tampered
        if str(row.id) in seen_bad:
            return
        seen_bad.add(str(row.id))
        tampered += 1
        if len(tampered_ids) < 100:
            tampered_ids.append(str(row.id))

    rows = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.tenant_id == tenant_id,  # F-026
    ).yield_per(500)
    for row in rows:
        checked += 1
        content_ok = False
        if row.hash_version is not None:
            # v3 (oder eine unbekannte Version — dann nie gueltig)
            content_ok = row.hash_version == audit_integrity.CURRENT_HASH_VERSION and audit_integrity.verify_row(row)
            if content_ok:
                ok += 1
            else:
                _bad(row)
        elif not row.row_hash:
            # A2-2: eine ungehashte Zeile, die JUENGER ist als die bei Migration
            # 076 festgehaltene Grenze, ist kein Altbestand — jemand hat die
            # Pruefsumme entfernt. Ohne Grenze (Mandant nach 076 angelegt oder
            # Grenze entfernt) gibt es keinen legitimen Altbestand.
            if legacy_cutoff is None or row.created_at is None or \
                    audit_integrity.canonical_timestamp(row.created_at) > legacy_cutoff:
                _bad(row)
            else:
                legacy += 1
        elif audit_integrity.verify_row(row):
            ok += 1
            content_ok = True
        elif _is_legacy_entry_row(row):
            legacy_deleted += 1
            if len(legacy_deleted_ids) < 100:
                legacy_deleted_ids.append(str(row.id))
        else:
            _bad(row)

        if row.chain_seq is None:
            unsealed += 1
        else:
            if not audit_integrity.verify_chain_link(row):
                _bad(row)
            links[row.chain_seq] = (row.chain_prev or "", row.chain_hash)
        if content_ok and row.action == PURGE_ACTION:
            purged |= parse_marker_seqs(row.new_note)
        if content_ok and row.action == REANCHOR_ACTION:
            reanchored += 1

    broken_links = 0
    for seq, (prev, _h) in links.items():
        before = links.get(seq - 1)
        if seq == 1 and prev != "":
            broken_links += 1
        elif before is not None and before[1] != prev:
            broken_links += 1

    top = max(links) if links else 0
    problem = head_problem(db, tenant_id, (top, links[top][1] if links else ""))
    head_ok = problem is None
    head = _read_head(db, tenant_id)
    if head_ok and head is not None:
        top = max(top, head[0])  # legitim entfernte letzte Glieder
    missing = [s for s in range(1, top + 1) if s not in links and s not in purged]

    return {
        "checked": checked,
        "ok": ok,
        "tampered": tampered,
        "legacy_unhashed": legacy,
        "legacy_entry_deleted": legacy_deleted,
        "unsealed": unsealed,
        "sealed": len(links),
        "missing_links": len(missing),
        "broken_links": broken_links,
        "head_ok": head_ok,
        "head_problem": problem,
        "reanchored": reanchored,
        "intact": tampered == 0 and not missing and broken_links == 0 and head_ok,
        "tampered_ids": tampered_ids,
        "missing_seqs": missing[:100],
        "legacy_entry_deleted_ids": legacy_deleted_ids,
    }


def _store_last_check(db: Session, tenant_id, result: dict, at: datetime) -> None:
    value = json.dumps({
        "checked_at": at.isoformat(),
        "intact": result["intact"],
        "checked": result["checked"],
        "tampered": result["tampered"],
        "missing_links": result["missing_links"],
        "head_ok": result["head_ok"],
    })
    row = db.query(SystemSetting).filter(
        SystemSetting.key == LAST_CHECK_SETTING_KEY, SystemSetting.tenant_id == tenant_id,
    ).first()
    if row is None:
        db.add(SystemSetting(key=LAST_CHECK_SETTING_KEY, tenant_id=tenant_id, value=value,
                             description="Änderungsprotokoll: letzte Prüfung (#537)"))
    else:
        row.value = value


def read_last_check(db: Session, tenant_id):
    row = db.query(SystemSetting).filter(
        SystemSetting.key == LAST_CHECK_SETTING_KEY, SystemSetting.tenant_id == tenant_id,
    ).first()
    if row is None:
        return None
    try:
        return json.loads(row.value)
    except ValueError:
        return None


def failure_detail(result: dict) -> str:
    return (
        f"Änderungsprotokoll: {result['tampered']} veränderte Zeile(n), "
        f"{result['missing_links']} fehlende Kettenglied(er), "
        f"{result['broken_links']} gebrochene Verknüpfung(en)"
        + ("" if result["head_ok"] else f", Kettenende {result.get('head_problem') or 'passt nicht'}")
        + f" — von {result['checked']} geprüften Zeilen."
    )


def check_tenant(db: Session, tenant_id, *, actor: str, record_failure: bool) -> dict:
    """Pruefen + versiegeln + Ergebnis ablegen; bei Abweichung (``record_failure``)
    ein ``security_events``-Vorgang und ein ``error_logs``-Eintrag. Committet.

    Erst pruefen, dann versiegeln: Versiegeln vor der Pruefung koennte einen
    Befund am Kettenende ueberschreiben. Stimmt das Kettenende nicht, wird
    nicht versiegelt (``seal_chain`` verweigert es ohnehin)."""
    result = verify_tenant(db, tenant_id)
    if result["head_ok"] and seal_chain(db, tenant_id):
        result = verify_tenant(db, tenant_id)
    now = datetime.now(timezone.utc)
    _store_last_check(db, tenant_id, result, now)
    if not result["intact"] and record_failure:
        db.add(SecurityEvent(
            tenant_id=tenant_id, event=EVENT_AUDIT_INTEGRITY_FAILED,
            actor=actor, detail=failure_detail(result),
        ))
    db.commit()
    if not result["intact"] and record_failure:
        try:
            from app.services.error_log_service import log_error
            log_error(db, "CRITICAL", "app.audit_integrity", failure_detail(result),
                      tenant_id=str(tenant_id))
        except Exception:  # noqa: BLE001 — Meldung ist best effort, der Vorgang steht schon
            db.rollback()
            logger.exception("audit integrity: error_logs-Eintrag fehlgeschlagen")
    return result


def reanchor_chain(db: Session, tenant_id, *, changed_by, reason: str) -> dict:
    """Setzt ein fehlendes oder ungueltiges Kettenende bewusst neu (Verwaltung,
    nach Klaerung). Hinterlaesst eine gehashte, sofort versiegelte Vermerk-Zeile
    mit Befund und Grund und einen ``security_events``-Vorgang — das Neusetzen
    selbst bleibt damit dauerhaft belegt. Was zwischen dem alten Kettenende und
    dem letzten vorhandenen Glied fehlte, ist nicht mehr feststellbar; das steht
    im Vermerk. Wirft ``ValueError``, wenn das Kettenende stimmt. Committet."""
    _lock_chain(db, tenant_id)
    db.flush()
    top_seq, top_hash = _chain_top(db, tenant_id)
    problem = head_problem(db, tenant_id, (top_seq, top_hash))
    if problem is None:
        raise ValueError("Das Kettenende ist in Ordnung — es gibt nichts neu zu setzen.")
    db.add(TimeEntryAuditLog(
        time_entry_id=None,
        user_id=changed_by,
        changed_by=changed_by,
        action=REANCHOR_ACTION,
        source=REANCHOR_SOURCE,
        old_note=f"Kettenende {problem}",
        new_note=(f"Kettenende neu gesetzt auf Glied {top_seq}; ob dahinter Zeilen "
                  f"entfernt wurden, ist nicht mehr feststellbar. Grund: {reason}"),
        tenant_id=tenant_id,
    ))
    db.flush()  # Vermerk-Zeile muss stehen: pz_audit_set_head erlaubt nur mit ihr ein Zuruecksetzen
    _write_head(db, tenant_id, top_seq, top_hash, reanchor=True)
    db.flush()
    seal_chain(db, tenant_id)
    db.add(SecurityEvent(
        tenant_id=tenant_id, event=EVENT_AUDIT_CHAIN_REANCHORED,
        actor=f"user:{changed_by}", detail=f"Kettenende {problem} — neu gesetzt auf Glied {top_seq}",
    ))
    db.commit()
    return check_tenant(db, tenant_id, actor=f"user:{changed_by}", record_failure=True)


def run_daily_check(db: Session) -> int:
    """Taeglicher Lauf (Scheduler, Superadmin-Kontext): jeder Mandant.
    Gibt die Zahl der Mandanten mit Abweichung zurueck."""
    failed = 0
    for (tenant_id,) in db.query(Tenant.id).all():
        try:
            result = check_tenant(db, tenant_id, actor="system:taeglich", record_failure=True)
        except Exception:  # noqa: BLE001 — ein Mandant darf die anderen nicht aufhalten
            db.rollback()
            logger.exception("audit integrity: Pruefung fuer Mandant %s fehlgeschlagen", tenant_id)
            continue
        if not result["intact"]:
            failed += 1
            logger.error("audit integrity: Mandant %s — %s", tenant_id, failure_detail(result))
    return failed
