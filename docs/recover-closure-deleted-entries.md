# Recovery: durch Betriebsferien gelöschte Zeiteinträge wiederherstellen (#290)

Bis zum Fix in #290 hat das **Anlegen / Neu-Speichern von Betriebsferien** auf den
abgedeckten Tagen vorhandene **Zeiteinträge gelöscht** (`company_closures.
_create_closure_absences`). Jede Löschung wurde aber im **Audit-Log** protokolliert
(`source='company_closure'`, `action='delete'`) **mit den alten Werten**
(`old_date` / `old_start_time` / `old_end_time` / `old_break_minutes` / `old_note`)
— die Einträge sind daher **wiederherstellbar**.

> Hinweis: `raw_start_time` / `raw_end_time` (§16-Rohstempel) liegen nicht im
> Audit-Log und werden nicht rekonstruiert — nur die regulären Zeiten.

## Ausführen

**Docker:**
```bash
docker compose exec -T db psql -U praxiszeit -d praxiszeit \
  -v tenant="'00000000-0000-0000-0000-000000000001'"   # Tenant-ID anpassen
```
**Nativ:** `bin/postgresql/bin/psql` über den Unix-Socket (siehe `INSTALL-NATIVE.md`),
gleiche `-v tenant=...`-Variable.

Erst die **PREVIEW** prüfen. Stimmt die Liste, den **RESTORE**-Block ausführen.
Idempotent — bereits vorhandene Einträge werden nicht doppelt angelegt.

## PREVIEW — was würde wiederhergestellt?

```sql
WITH candidates AS (
    SELECT DISTINCT ON (a.user_id, a.old_date, a.old_start_time)
           a.user_id, a.tenant_id, a.old_date, a.old_start_time,
           a.old_end_time, a.old_break_minutes, a.old_note, a.created_at AS deleted_at
    FROM time_entry_audit_logs a
    WHERE a.source = 'company_closure' AND a.action = 'delete'
      AND a.tenant_id = :tenant::uuid
      AND a.old_date IS NOT NULL
    ORDER BY a.user_id, a.old_date, a.old_start_time, a.created_at DESC
)
SELECT c.user_id, c.old_date, c.old_start_time, c.old_end_time,
       c.old_break_minutes, c.deleted_at
FROM candidates c
WHERE NOT EXISTS (
    SELECT 1 FROM time_entries t
    WHERE t.user_id = c.user_id AND t.date = c.old_date
      AND t.start_time IS NOT DISTINCT FROM c.old_start_time
)
ORDER BY c.user_id, c.old_date;
```

## RESTORE — Einträge wieder anlegen

```sql
BEGIN;
WITH candidates AS (
    SELECT DISTINCT ON (a.user_id, a.old_date, a.old_start_time)
           a.user_id, a.tenant_id, a.old_date, a.old_start_time,
           a.old_end_time, a.old_break_minutes, a.old_note
    FROM time_entry_audit_logs a
    WHERE a.source = 'company_closure' AND a.action = 'delete'
      AND a.tenant_id = :tenant::uuid AND a.old_date IS NOT NULL
    ORDER BY a.user_id, a.old_date, a.old_start_time, a.created_at DESC
)
INSERT INTO time_entries (id, user_id, tenant_id, date, start_time, end_time, break_minutes, note)
SELECT gen_random_uuid(), c.user_id, c.tenant_id, c.old_date, c.old_start_time,
       c.old_end_time, COALESCE(c.old_break_minutes, 0), c.old_note
FROM candidates c
WHERE NOT EXISTS (
    SELECT 1 FROM time_entries t
    WHERE t.user_id = c.user_id AND t.date = c.old_date
      AND t.start_time IS NOT DISTINCT FROM c.old_start_time
);
COMMIT;
```

Pro `(user, Tag, Startzeit)` wird nur die **zuletzt** gelöschte Version
wiederhergestellt (mehrfaches Neu-Speichern erzeugte mehrere `delete`-Logs), und nur,
wenn aktuell **kein** passender Eintrag existiert.
