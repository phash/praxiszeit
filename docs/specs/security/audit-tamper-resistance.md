# Audit-Log Tamper-Resistance — Design-Spec

**Issue:** [#121](https://github.com/phash/praxiszeit/issues/121)
**Status:** Vorschlag · zur Entscheidung
**Autor:** Claude Opus 4.7
**Datum:** 24. Mai 2026

---

## Problem

Die Tabelle `time_entry_audit_logs` ist heute **konsistent beim Schreiben**, aber **nicht integritätsgeschützt nach dem Schreiben**:

- Schreibender DB-User ist `praxiszeit_app` (gleicher User wie alle App-Lesezugriffe)
- Eine SQL-Injection an anderer Stelle könnte Audit-Rows nachträglich modifizieren oder löschen
- Keine Hash-Chain, keine Signatur, kein Tamper-Evidence

Der interne Review nannte das Audit-Log "tamper-resistant" — das ist faktisch falsch. Für ein DSGVO/ArbZG-Tool, das Mitarbeiter-Arbeitszeiten 2 Jahre revisionssicher halten muss (§ 16 ArbZG), ist das eine Lücke mit Audit-Findings-Potenzial.

**Bedrohungsszenario:** Ein Angreifer findet eine SQL-Injection in einem ungewohnten Endpoint (z. B. Report-Filter, Bulk-Import), kann mit `praxiszeit_app`-Rechten arbiträre SQL ausführen, und ändert/löscht Audit-Rows, um seine Spuren zu verwischen. Aktuell **unauffällig durchführbar**.

---

## Was schon existiert

- `time_entry_audit_logs` mit FKs auf tenant/user/changed_by, old/new-Werte, action, source, created_at
- RLS-Policy enforced auf tenant-Ebene
- Append-Pattern in App-Code: keine bekannten Stellen wo wir Audit-Rows updaten oder deleten (außer `purge_expired_vacation_audit_logs` für Art. 5 (1)(e) Speicherbegrenzung — kontrollierter Löschpfad nach 730 Tagen)

---

## Optionen

### Option A — Append-Only DB-Role

**Idee:** Neue Postgres-Rolle `praxiszeit_audit` mit nur `INSERT`-Privileg auf `time_entry_audit_logs`. App nutzt zwei Connection-Pools:
- normaler Pool (`praxiszeit_app`) für Lese-Zugriffe und alle anderen Schreib-Operationen
- Audit-Pool (`praxiszeit_audit`) für Audit-Inserts

UPDATEs und DELETEs auf `time_entry_audit_logs` werden auf Postgres-Ebene verweigert. Eine SQL-Injection im Hauptpool kann Audit-Rows nicht mehr ändern.

**Migration:**
```sql
CREATE ROLE praxiszeit_audit LOGIN PASSWORD '...';
GRANT USAGE ON SCHEMA public TO praxiszeit_audit;
GRANT INSERT ON time_entry_audit_logs TO praxiszeit_audit;
GRANT USAGE, SELECT ON SEQUENCE time_entry_audit_logs_id_seq TO praxiszeit_audit;
-- WICHTIG: kein SELECT/UPDATE/DELETE!

REVOKE UPDATE, DELETE ON time_entry_audit_logs FROM praxiszeit_app;
-- (SELECT bleibt, sonst kann Admin den Audit-Log nicht lesen)
```

**App-Anpassung:**
- Neuer SQLAlchemy-Engine `audit_engine` mit `AUDIT_DB_PASSWORD`
- `audit_session_maker = sessionmaker(bind=audit_engine)`
- Helper `with_audit_session()` Context-Manager
- Audit-Inserts werden in einer eigenen Transaktion auf der Audit-Connection committed (separate Tx → bei Rollback der Haupt-Tx bleibt die Audit-Row stehen, **das ist Absicht**: der Versuch war da, wir wollen ihn dokumentieren)

**Vorteile:**
- Postgres-Level-Garantie, kryptografisch nicht umgehbar (ohne DB-Admin-Compromise)
- Keine App-seitige Hash-Verifikation, kein neuer Verify-Job nötig
- Keine Schlüssel zu rotieren

**Nachteile:**
- Zwei Connections pro Audit-relevanter Operation (Pool-Doubling)
- `purge_expired_vacation_audit_logs` muss als **dritter** DB-User laufen (`praxiszeit_purge`?) oder als Superuser → mehr Privilege-Splitting
- Migration auf Bestands-DBs: existierende Audit-Rows sind retroaktiv NICHT geschützt, nur neue
- Konnektivität: Native-Installer muss zwei Passwörter generieren + verwalten (`config/.db-credentials` Schema-Erweiterung)

**Restrisiko:** DB-Admin-Compromise (z. B. Backup-Restore mit manipulierter Tabelle) bleibt möglich.

---

### Option B — HMAC-Hash-Chain

**Idee:** Jede Audit-Row enthält zwei neue Spalten:
- `prev_hash BYTEA NOT NULL` — Hash der vorherigen Row in der Chain
- `row_hash BYTEA NOT NULL` — HMAC-SHA256 über `(id, prev_hash, tenant_id, user_id, changed_by, action, source, created_at, payload-Felder)` mit Server-Secret

Beim Insert: Lookup der letzten Row (per `tenant_id`-Chain), Berechnung der Hashes, Insert mit beiden Werten. Eine nachträgliche Mutation einzelner Felder bricht den `row_hash`. Ein nachträgliches Löschen einer Row bricht die Verkettung der nachfolgenden Rows (`prev_hash` zeigt auf nicht-existente ID).

**Migration:**
```sql
ALTER TABLE time_entry_audit_logs ADD COLUMN prev_hash BYTEA;
ALTER TABLE time_entry_audit_logs ADD COLUMN row_hash BYTEA;

-- Backfill: existierende Rows bekommen prev_hash=NULL und row_hash über
-- die bestehenden Felder berechnet. NICHT retroaktiv signiert (kein Secret
-- der "rückwirkenden Wahrheit"), aber der Genesis-Punkt der Chain wird
-- als "ab heute geprueft" dokumentiert.
```

**Schlüsselmanagement:**
- `AUDIT_HMAC_KEY` als Env-Variable, mindestens 32 Bytes, einmalig generiert per Tenant
- Native-Installer: in `config/.audit-hmac-key` ablegen, gleiche Permissions wie `.secret-key`
- Docker: in `.env`, dokumentiert in der Setup-Anleitung
- **Rotation:** komplex. Bei Key-Rotation müssten alle Rows neu signiert werden → reset der Chain mit "Rotation-Marker"-Row

**Verify-Endpoint:**
- `GET /api/admin/audit/verify-integrity` läuft Tenant-weit durch die Chain
- Liefert pro Tenant `{ok: bool, broken_at_id: uuid?, last_valid: timestamp, total_rows: int}`
- Im Idealfall als Cron-Job täglich, Resultat in einer separaten `audit_integrity_check`-Tabelle

**Vorteile:**
- Kryptografische Tamper-Evidence — Mutation wird **detektiert**, auch wenn nicht **verhindert**
- Keine DB-Privilege-Trennung nötig
- Funktioniert auch bei Backup-Restore-Tampering (Verify nach Restore findet die Lücke)

**Nachteile:**
- Performance: jeder Insert braucht einen SELECT auf die letzte Chain-Row (mit `FOR UPDATE` um Race-Conditions zu vermeiden) → ein Round-Trip mehr pro Audit-Operation
- DSGVO Art. 17 Löschungen brechen die Chain (gewollt, aber Verify-Job muss "geplante Lücken" erkennen können)
- Schlüsselmanagement: Verlust des HMAC-Key macht Verifikation unmöglich (alle Rows werden "ungültig" markiert)
- Verify-Endpoint kann lang laufen bei großen Audit-Tabellen (10k+ Rows) → Background-Job statt Online-Endpoint

**Restrisiko:** Wer den `AUDIT_HMAC_KEY` hat, kann Rows neu signieren. Key muss separat vom App-Secret geschützt sein (eigene Datei, eigene Permissions, idealerweise HSM/KMS in SaaS-Setup).

---

### Option C — Beides (Defense-in-Depth)

Append-Only-Role **plus** HMAC-Chain. Eine SQL-Injection im Haupt-Pool kann Audit-Rows nicht ändern (Option A); ein DB-Admin-Tampering wird beim nächsten Verify-Lauf erkannt (Option B).

**Aufwand:** ~5 Tage statt 2-3 für einzelne Option.

**Wann sinnvoll:** Wenn die Compliance-Anforderung explizit "Defense-in-Depth" oder "Mehrfaktorielle Tamper-Detection" fordert (BAIT, KRITIS, ISO 27001 in stark regulierten Branchen). Für eine Arztpraxis nicht zwingend.

---

## Vergleichsmatrix

| Kriterium | A (Role) | B (HMAC) | C (Beides) |
|---|---|---|---|
| Aufwand Implementierung | 2 Tage | 3 Tage | 5 Tage |
| Migration auf Bestands-DBs | Niedrig (1 Migration + Passwort-Gen) | Mittel (Spalten + Backfill + Key-Gen) | Mittel-Hoch |
| Verhindert SQL-Injection-Tampering | ✅ Ja | ❌ Nein (nur detect) | ✅ Ja |
| Detektiert Backup-Restore-Tampering | ❌ Nein | ✅ Ja | ✅ Ja |
| Schlüsselmanagement-Overhead | Keiner | Mittel (Audit-HMAC-Key) | Mittel |
| Performance-Impact pro Insert | Vernachlässigbar | +1 SELECT pro Insert | +1 SELECT pro Insert |
| Native-Installer-Komplexität | Mittel (2 DB-Users) | Niedrig (1 Datei mehr) | Hoch |
| Docker-Compose-Aenderung | +1 ENV-Var, init-Skript Update | +1 ENV-Var | +2 ENV-Vars |
| DSGVO Art. 17 Verträglichkeit | ✅ (purge-Pfad als 3. Role) | ⚠ (Chain-Lücke akzeptabel) | ⚠ (beide Caveats) |
| Verify-Job nötig | Nein | Ja (täglich) | Ja |

---

## Empfehlung

**Option B (HMAC-Hash-Chain).**

Begründung:
1. **Größeres Bedrohungsmodell abgedeckt** — detektiert sowohl SQL-Injection-Tampering (nach Verify-Lauf) als auch Backup-Restore-Tampering. Option A schützt nur gegen ersteres.
2. **Niedrigerer Installer-Aufwand** — eine zusätzliche Datei (`.audit-hmac-key`) statt zweier DB-User mit eigenem Pool. Wichtig für Native-Windows-Setup, das ohnehin schon viele Edge-Cases hat.
3. **DSGVO-konformer Art.-17-Pfad** — die Chain-Lücke nach einer Löschung ist akzeptabel und dokumentierbar (Verify-Job kennt geplante Lücken aus der `purge_expired_vacation_audit_logs`-Operation).
4. **Performance-Kosten überschaubar** — `SELECT ... FOR UPDATE` auf den letzten Row der Tenant-Chain ist O(1) mit Index auf `(tenant_id, created_at DESC)`. Pro Audit-Insert eine zusätzliche DB-Round-Trip (~1 ms in LAN).

**Wenn später Defense-in-Depth gewünscht ist:** Option A kann nachträglich draufgesetzt werden (Append-Only-Role-Migration ist unabhängig vom HMAC-Pfad).

---

## Implementierungs-Skizze (Option B)

### Phase 1 — Schema + Genesis (½ Tag)

- Migration `038_audit_log_hmac_chain.py`:
  - Add columns `prev_hash BYTEA NULL`, `row_hash BYTEA NULL` (nullable für Backfill-Phase)
  - Index `(tenant_id, created_at DESC, id)` für den Chain-Tail-Lookup
- Backfill-Skript: pro Tenant alle Rows nach `(created_at, id)` sortiert durchlaufen, `prev_hash` setzen, `row_hash` aus aktuellen Feldern + Secret berechnen
- Genesis-Marker: pro Tenant eine `genesis`-Row mit `prev_hash=NULL`, `row_hash=HMAC(tenant_id || "GENESIS")` einfügen
- Nach Backfill: `ALTER COLUMN ... SET NOT NULL`

### Phase 2 — App-Integration (1 Tag)

- `app/services/audit_chain_service.py`:
  - `compute_row_hash(secret, prev_hash, row_dict) → bytes`
  - `next_chain_link(db, tenant_id) → (prev_hash, prev_id)` mit `SELECT ... FOR UPDATE`
  - `sign_and_insert(db, audit_log_row, secret) → TimeEntryAuditLog` — Komplett-Operation atomar
- Alle `db.add(TimeEntryAuditLog(...))` Stellen umstellen auf `audit_chain_service.sign_and_insert(...)` (ca. 12 Stellen in `time_entries.py`, `admin_*.py`, `vacation_requests.py`, `me.py` neu)
- Secret-Loading: `settings.AUDIT_HMAC_KEY` (env), Native lädt aus `config/.audit-hmac-key`, Auto-Generate beim ersten Start wenn fehlt

### Phase 3 — Verify-Job + Admin-UI (1 Tag)

- `app/services/audit_verify_service.py`: `verify_tenant_chain(db, tenant_id, secret) → VerificationResult`
- Endpoint `GET /api/admin/audit/verify-integrity` (require_admin, tenant-scoped, async für große Chains)
- Cron-Job in `main.py`-Startup (oder Native-Server.py): täglich um 03:30, Resultat in `audit_integrity_check`-Tabelle
- Admin-UI: kleine Card im Dashboard "Audit-Integrität: ✅ 47.235 Rows OK, letzter Check 24.05.2026 03:30" / "⚠ Inkonsistenz bei Row $UUID, Check stoppt — sofort Admin informieren"

### Phase 4 — Doku (½ Tag)

- `docs/SECURITY.md` (neu schreiben — heute nur Template): Threat-Model, Audit-Tamper-Resistance, Key-Management
- `docs/specs/dsgvo/verarbeitungsverzeichnis.md`: TOM "Eingabekontrolle" verschärfen ("HMAC-Hash-Chain mit täglicher Verifikation")
- `docs/INSTALL-NATIVE.md`: `.audit-hmac-key`-Datei dokumentieren, Rotations-Hinweis

---

## Migrations-Plan auf Produktions-DBs

Reihenfolge:
1. Backup ziehen
2. Migration 038 anwenden (Schema-Änderung)
3. Backfill-Skript laufen lassen (ca. 1 Min pro 10.000 Rows in Tests)
4. App-Restart mit neuem Code
5. `SET NOT NULL` Migration 039
6. Verify-Job einmalig manuell ausführen → muss alle existierenden Rows als "valid" markieren
7. Admin-UI freischalten

**Rollback:** Spalten droppen, App-Code zurück auf alten Stand, Audit-Logs werden weiter ohne Chain geschrieben (nicht-destruktiv).

---

## Offene Fragen

- **Key-Rotation:** Lösung A "Rotation-Marker-Row + neuer Chain-Start mit altem Hash als prev_hash" — robust aber komplex. Lösung B "Re-sign aller Rows mit neuem Key" — einfach aber lang-laufende Operation. Entscheidung vor Implementierung nötig.
- **Multi-Tenant-Chain-Isolation:** Pro Tenant eine eigene Chain (so geplant). Alternative: globale Chain mit tenant_id im Hash. Pro-Tenant ist sauberer wegen Tenant-Deaktivierung/Löschung.
- **Performance bei Bulk-Insert** (z. B. XLS-Import mit 1000 Zeiteinträgen): jeder einzelne Eintrag erzeugt eine Audit-Row mit Chain-Lookup. Im worst case 1000× `FOR UPDATE` auf der Tenant-Chain → Serialisierung. **Mitigation:** Bulk-Insert berechnet die Chain in einem Pass im App-Code und macht einen einzelnen `INSERT ... RETURNING`. Implementation in Phase 2 als Sonder-Pfad.
- **Verifikations-Performance:** Bei 100.000 Rows ist ein voller Re-Hash-Lauf nicht O(1). Inkrementelle Verifikation (`last_verified_id` cachen, ab dort weiter) als Optimierung in Phase 3 — Anforderung dokumentieren, Implementation falls Bedarf.

---

## Referenzen

- Issue [#121](https://github.com/phash/praxiszeit/issues/121)
- Original-Review: `docs/superpowers/reports/2026-05-06-vacation-request-edit-review.md` (P4.2 INFO-1)
- Vergleichbare Implementierungen: PostgreSQL `pgcrypto` HMAC-Funktionen, AWS QLDB (Append-Only-Ledger als Service)
- DSGVO Art. 32 (1)(b) "Vertraulichkeit, Integrität, Verfügbarkeit" — Integrität fließt direkt in dieses Design ein
- ArbZG § 16 — 2-Jahres-Aufbewahrung; Tamper-Resistance ist nicht explizit gefordert, aber Aufsichts-konforme Auslegung
