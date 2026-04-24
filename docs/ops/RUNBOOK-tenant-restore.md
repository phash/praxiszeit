# Runbook: Tenant-Restore aus Daily-PG-Dump

Dieses Dokument beschreibt, wie Daten eines einzelnen Tenants aus dem
täglichen PostgreSQL-Dump wiederhergestellt werden, ohne den gesamten
Cluster zurückzurollen.

## Voraussetzungen

- Zugriff auf das Backup-Verzeichnis (per Policy: 30 Tage Aufbewahrung,
  verschlüsselt).
- `psql` + `pg_dump` auf dem Restore-Host (Version ≥ 16).
- Kenntnis der betroffenen `tenant_id` (UUID).

## Fall 1 — Einzelner Tenant hat versehentlich Daten gelöscht

1. **Scratch-DB erstellen**:
   ```bash
   createdb -U praxiszeit_migrations praxiszeit_restore_$(date +%s)
   ```
2. **Kompletten Dump einspielen**:
   ```bash
   pg_restore --no-owner -d praxiszeit_restore_XXXX /backups/praxiszeit_YYYYMMDD.dump
   ```
3. **Nur betroffene Zeilen exportieren**:
   ```bash
   TENANT="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

   # Time entries
   pg_dump --data-only \
     --table=time_entries \
     --table=absences \
     --table=change_requests \
     --where="tenant_id='${TENANT}'" \
     praxiszeit_restore_XXXX > tenant_slice.sql
   ```
   (`--where` benötigt `pg_dump` ≥ 17; alternativ per `COPY (SELECT ... WHERE tenant_id=...) TO`.)
4. **Diff gegen Live-DB**: vor `psql -f` in eine Staging-Kopie der
   Live-DB einspielen und dort verifizieren.
5. **Apply auf Live**: nur dann, wenn Schritt 4 erfolgreich war.

## Fall 2 — Tenant komplett verloren (Account irrtümlich anonymisiert)

Die Migration 036 + `lifecycle_service.anonymize_tenant` scrubt PII,
aber behält die Zeilen. Wenn die 30-Tage-Grace umgangen wurde:

1. Scratch-DB wie oben.
2. Daten direkt für die `tenant_id` abfragen und per `COPY` rüber­ziehen.
3. User-Spalten (`username`, `email`, `first_name`, `last_name`, `password_hash`)
   zurückspielen. Tenant-Spalten (`name`, `company_name`, …) analog.

## Monitoring / Verification

- `praxiszeit_tenant_employees{tenant_id="…"}` muss in Grafana wieder die
  erwartete Zahl zeigen.
- `praxiszeit_tenant_dau` kehrt am Folgetag zurück (DAU-Fenster = 24 h).

## Backup-Policy (Ist-Zustand)

- Täglich 02:00 UTC: `pg_dump -Fc` auf gleichem Host, `rsync` auf externe
  Backup-Maschine.
- Retention: 30 Tage rolling.
- Off-Site-Kopie: wöchentlich, verschlüsselt (GPG).

> Wenn Backups nicht konfiguriert sind, sofort Phase 7 Ops-Task aufsetzen
> – **das Produkt ist nicht SaaS-tauglich ohne Restore-Pfad.**
