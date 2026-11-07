-- Create non-superuser app role for RLS enforcement.
-- This script runs on first database initialization only.
-- The password is applied by init-db-user.sh (same directory) which reads
-- APP_DB_PASSWORD from the container environment and executes
-- ALTER ROLE praxiszeit_app PASSWORD '...' after this script.
-- F-025: never leave this role with a NULL password in case the .sh step
-- is skipped — unlogin-able role fails closed rather than open.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'praxiszeit_app') THEN
        CREATE ROLE praxiszeit_app LOGIN NOINHERIT;
    END IF;
END
$$;

-- Grant permissions on the database
GRANT CONNECT ON DATABASE praxiszeit TO praxiszeit_app;
GRANT USAGE ON SCHEMA public TO praxiszeit_app;

-- Grant table permissions (current and future tables)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO praxiszeit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO praxiszeit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO praxiszeit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO praxiszeit_app;

-- #537 (Migration 076): das Aenderungsprotokoll ist fuer die App-Rolle nur
-- anfuegbar. Laeuft dieses Skript erneut (Wiederherstellung, CI), vergibt die
-- Zeile oben UPDATE/DELETE wieder — hier sofort zurueck. Der Trigger
-- pz_audit_guard verweigert beides ohnehin; das hier haelt die Rechteliste ehrlich.
DO $$
BEGIN
    IF to_regclass('public.time_entry_audit_logs') IS NOT NULL THEN
        REVOKE UPDATE, DELETE, TRUNCATE ON time_entry_audit_logs FROM praxiszeit_app;
    END IF;
    -- Grabsteine geloeschter Protokollzeilen (Review-Runde 3): nur die
    -- Eigentuemerin; die App-Rolle darf sie weder lesen noch schreiben.
    IF to_regclass('public.audit_log_tombstones') IS NOT NULL THEN
        REVOKE ALL ON audit_log_tombstones FROM praxiszeit_app;
    END IF;
    -- Jede je vergebene Protokoll-id (Review-Runde 5): ebenso nur die Eigentuemerin.
    IF to_regclass('public.audit_log_ids') IS NOT NULL THEN
        REVOKE ALL ON audit_log_ids FROM praxiszeit_app;
    END IF;
END
$$;

-- #537 (Migration 076): die Protokollfunktionen nur fuer die App-Rolle
-- ausfuehrbar, nicht fuer PUBLIC (PostgreSQL-Vorgabe beim Anlegen).
DO $$
DECLARE
    f text;
BEGIN
    FOREACH f IN ARRAY ARRAY[
        'pz_audit_seal(uuid[], bigint[], text[], text[])',
        'pz_audit_set_notes(uuid, text, text, text)',
        'pz_audit_delete(uuid[])',
        'pz_audit_tenant_ok(uuid)',
        'pz_audit_head_seq(uuid)',
        'pz_audit_set_head(uuid, text, boolean)',
        'pz_audit_scrub_ok(text, text)',
        'pz_audit_tombstoned(uuid)'
    ] LOOP
        IF to_regprocedure(f) IS NOT NULL THEN
            -- ohne Prozent-Platzhalter: Tests reichen die Datei durch psycopg
            EXECUTE 'REVOKE EXECUTE ON FUNCTION ' || f || ' FROM PUBLIC';
            EXECUTE 'GRANT EXECUTE ON FUNCTION ' || f || ' TO praxiszeit_app';
        END IF;
    END LOOP;
END
$$;

-- #537 (Migration 076, Review-Runde 7): die Triggerfunktion, die jede
-- Protokoll-id fest vergibt, gehoert nur dem Trigger. EXECUTE braucht nur
-- CREATE TRIGGER - ohne das Recht kann die App-Rolle sie nicht an eine eigene
-- (temporaere) Tabelle haengen. Die WHEN-Bedingung der Vergabe-Trigger laeuft
-- als schreibendes Konto und braucht EXECUTE - ausdruecklich vergeben, falls
-- eine Wiederherstellung die PUBLIC-Vorgabe entzogen hat.
DO $$
BEGIN
    IF to_regprocedure('pz_audit_claim()') IS NOT NULL THEN
        REVOKE ALL ON FUNCTION pz_audit_claim() FROM PUBLIC;
        REVOKE ALL ON FUNCTION pz_audit_claim() FROM praxiszeit_app;
    END IF;
    IF to_regprocedure('pz_audit_writer_is_owner()') IS NOT NULL THEN
        GRANT EXECUTE ON FUNCTION pz_audit_writer_is_owner() TO praxiszeit_app;
    END IF;
END
$$;
