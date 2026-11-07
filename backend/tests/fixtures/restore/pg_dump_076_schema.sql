--
-- PostgreSQL database dump
--

\restrict SgZtr7I2mhqxWXjZwJKHxRDi9JP12VoFnIvsQbl1iNNzoGiLhmRtA1h6QZcb58k

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

DROP POLICY IF EXISTS tenant_isolation ON public.year_carryovers;
DROP POLICY IF EXISTS tenant_isolation ON public.workstations;
DROP POLICY IF EXISTS tenant_isolation ON public.workstation_qualifications;
DROP POLICY IF EXISTS tenant_isolation ON public.working_hours_changes;
DROP POLICY IF EXISTS tenant_isolation ON public.vacation_requests;
DROP POLICY IF EXISTS tenant_isolation ON public.users;
DROP POLICY IF EXISTS tenant_isolation ON public.time_entry_audit_logs;
DROP POLICY IF EXISTS tenant_isolation ON public.time_entries;
DROP POLICY IF EXISTS tenant_isolation ON public.tenants;
DROP POLICY IF EXISTS tenant_isolation ON public.tenant_invoices;
DROP POLICY IF EXISTS tenant_isolation ON public.system_settings;
DROP POLICY IF EXISTS tenant_isolation ON public.stripe_events;
DROP POLICY IF EXISTS tenant_isolation ON public.signup_tokens;
DROP POLICY IF EXISTS tenant_isolation ON public.signup_audit_log;
DROP POLICY IF EXISTS tenant_isolation ON public.shift_slots;
DROP POLICY IF EXISTS tenant_isolation ON public.shift_plans;
DROP POLICY IF EXISTS tenant_isolation ON public.shift_assignments;
DROP POLICY IF EXISTS tenant_isolation ON public.security_events;
DROP POLICY IF EXISTS tenant_isolation ON public.reduced_days;
DROP POLICY IF EXISTS tenant_isolation ON public.public_holidays;
DROP POLICY IF EXISTS tenant_isolation ON public.locations;
DROP POLICY IF EXISTS tenant_isolation ON public.impersonation_sessions;
DROP POLICY IF EXISTS tenant_isolation ON public.error_logs;
DROP POLICY IF EXISTS tenant_isolation ON public.company_closures;
DROP POLICY IF EXISTS tenant_isolation ON public.change_requests;
DROP POLICY IF EXISTS tenant_isolation ON public.audit_log_tombstones;
DROP POLICY IF EXISTS tenant_isolation ON public.audit_log_ids;
DROP POLICY IF EXISTS tenant_isolation ON public.absences;
DROP POLICY IF EXISTS tenant_isolation ON public.absence_reasons;
ALTER TABLE IF EXISTS ONLY public.year_carryovers DROP CONSTRAINT IF EXISTS year_carryovers_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.workstations DROP CONSTRAINT IF EXISTS workstations_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.workstations DROP CONSTRAINT IF EXISTS workstations_location_id_fkey;
ALTER TABLE IF EXISTS ONLY public.workstation_qualifications DROP CONSTRAINT IF EXISTS workstation_qualifications_workstation_id_fkey;
ALTER TABLE IF EXISTS ONLY public.workstation_qualifications DROP CONSTRAINT IF EXISTS workstation_qualifications_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.workstation_qualifications DROP CONSTRAINT IF EXISTS workstation_qualifications_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.working_hours_changes DROP CONSTRAINT IF EXISTS working_hours_changes_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vacation_requests DROP CONSTRAINT IF EXISTS vacation_requests_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.vacation_requests DROP CONSTRAINT IF EXISTS vacation_requests_reviewed_by_fkey;
ALTER TABLE IF EXISTS ONLY public.vacation_requests DROP CONSTRAINT IF EXISTS vacation_requests_last_modified_by_fkey;
ALTER TABLE IF EXISTS ONLY public.time_entry_audit_logs DROP CONSTRAINT IF EXISTS time_entry_audit_logs_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.time_entry_audit_logs DROP CONSTRAINT IF EXISTS time_entry_audit_logs_time_entry_id_fkey;
ALTER TABLE IF EXISTS ONLY public.time_entry_audit_logs DROP CONSTRAINT IF EXISTS time_entry_audit_logs_changed_by_fkey;
ALTER TABLE IF EXISTS ONLY public.time_entry_audit_logs DROP CONSTRAINT IF EXISTS time_entry_audit_logs_change_request_id_fkey;
ALTER TABLE IF EXISTS ONLY public.time_entries DROP CONSTRAINT IF EXISTS time_entries_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.shift_slots DROP CONSTRAINT IF EXISTS shift_slots_workstation_id_fkey;
ALTER TABLE IF EXISTS ONLY public.shift_slots DROP CONSTRAINT IF EXISTS shift_slots_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.shift_slots DROP CONSTRAINT IF EXISTS shift_slots_shift_plan_id_fkey;
ALTER TABLE IF EXISTS ONLY public.shift_plans DROP CONSTRAINT IF EXISTS shift_plans_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.shift_plans DROP CONSTRAINT IF EXISTS shift_plans_created_by_fkey;
ALTER TABLE IF EXISTS ONLY public.shift_assignments DROP CONSTRAINT IF EXISTS shift_assignments_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.shift_assignments DROP CONSTRAINT IF EXISTS shift_assignments_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.shift_assignments DROP CONSTRAINT IF EXISTS shift_assignments_shift_slot_id_fkey;
ALTER TABLE IF EXISTS ONLY public.security_events DROP CONSTRAINT IF EXISTS security_events_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.security_events DROP CONSTRAINT IF EXISTS security_events_subject_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.reduced_days DROP CONSTRAINT IF EXISTS reduced_days_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.reduced_days DROP CONSTRAINT IF EXISTS reduced_days_created_by_fkey;
ALTER TABLE IF EXISTS ONLY public.locations DROP CONSTRAINT IF EXISTS locations_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.impersonation_sessions DROP CONSTRAINT IF EXISTS impersonation_sessions_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.impersonation_sessions DROP CONSTRAINT IF EXISTS impersonation_sessions_target_id_fkey;
ALTER TABLE IF EXISTS ONLY public.impersonation_sessions DROP CONSTRAINT IF EXISTS impersonation_sessions_impersonator_id_fkey;
ALTER TABLE IF EXISTS ONLY public.year_carryovers DROP CONSTRAINT IF EXISTS fk_year_carryovers_tenant_id;
ALTER TABLE IF EXISTS ONLY public.working_hours_changes DROP CONSTRAINT IF EXISTS fk_working_hours_changes_tenant_id;
ALTER TABLE IF EXISTS ONLY public.vacation_requests DROP CONSTRAINT IF EXISTS fk_vacation_requests_tenant_id;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS fk_users_tenant_id;
ALTER TABLE IF EXISTS ONLY public.time_entry_audit_logs DROP CONSTRAINT IF EXISTS fk_time_entry_audit_logs_tenant_id;
ALTER TABLE IF EXISTS ONLY public.time_entries DROP CONSTRAINT IF EXISTS fk_time_entries_tenant_id;
ALTER TABLE IF EXISTS ONLY public.tenant_invoices DROP CONSTRAINT IF EXISTS fk_tenant_invoices_tenant_id;
ALTER TABLE IF EXISTS ONLY public.system_settings DROP CONSTRAINT IF EXISTS fk_system_settings_tenant_id;
ALTER TABLE IF EXISTS ONLY public.signup_tokens DROP CONSTRAINT IF EXISTS fk_signup_tokens_user_id;
ALTER TABLE IF EXISTS ONLY public.signup_tokens DROP CONSTRAINT IF EXISTS fk_signup_tokens_tenant_id;
ALTER TABLE IF EXISTS ONLY public.public_holidays DROP CONSTRAINT IF EXISTS fk_public_holidays_tenant_id;
ALTER TABLE IF EXISTS ONLY public.error_logs DROP CONSTRAINT IF EXISTS fk_error_logs_tenant_id;
ALTER TABLE IF EXISTS ONLY public.company_closures DROP CONSTRAINT IF EXISTS fk_company_closures_tenant_id;
ALTER TABLE IF EXISTS ONLY public.change_requests DROP CONSTRAINT IF EXISTS fk_change_requests_tenant_id;
ALTER TABLE IF EXISTS ONLY public.change_requests DROP CONSTRAINT IF EXISTS fk_change_requests_absence_id;
ALTER TABLE IF EXISTS ONLY public.absences DROP CONSTRAINT IF EXISTS fk_absences_tenant_id;
ALTER TABLE IF EXISTS ONLY public.absences DROP CONSTRAINT IF EXISTS fk_absences_closure_id;
ALTER TABLE IF EXISTS ONLY public.error_logs DROP CONSTRAINT IF EXISTS error_logs_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.error_logs DROP CONSTRAINT IF EXISTS error_logs_resolved_by_fkey;
ALTER TABLE IF EXISTS ONLY public.company_closures DROP CONSTRAINT IF EXISTS company_closures_created_by_fkey;
ALTER TABLE IF EXISTS ONLY public.change_requests DROP CONSTRAINT IF EXISTS change_requests_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.change_requests DROP CONSTRAINT IF EXISTS change_requests_time_entry_id_fkey;
ALTER TABLE IF EXISTS ONLY public.change_requests DROP CONSTRAINT IF EXISTS change_requests_reviewed_by_fkey;
ALTER TABLE IF EXISTS ONLY public.change_requests DROP CONSTRAINT IF EXISTS change_requests_proposed_reason_id_fkey;
ALTER TABLE IF EXISTS ONLY public.audit_log_tombstones DROP CONSTRAINT IF EXISTS audit_log_tombstones_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.audit_log_ids DROP CONSTRAINT IF EXISTS audit_log_ids_tenant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.absences DROP CONSTRAINT IF EXISTS absences_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.absences DROP CONSTRAINT IF EXISTS absences_reason_id_fkey;
ALTER TABLE IF EXISTS ONLY public.absence_reasons DROP CONSTRAINT IF EXISTS absence_reasons_tenant_id_fkey;
DROP TRIGGER IF EXISTS pz_audit_head_guard_write ON public.system_settings;
DROP TRIGGER IF EXISTS pz_audit_guard_write ON public.time_entry_audit_logs;
DROP INDEX IF EXISTS public.uq_audit_tenant_chain_seq;
DROP INDEX IF EXISTS public.ix_year_carryovers_user_id;
DROP INDEX IF EXISTS public.ix_year_carryovers_tenant_id;
DROP INDEX IF EXISTS public.ix_workstations_tenant_id;
DROP INDEX IF EXISTS public.ix_workstations_location_id;
DROP INDEX IF EXISTS public.ix_workstation_qualifications_workstation_id;
DROP INDEX IF EXISTS public.ix_workstation_qualifications_user_id;
DROP INDEX IF EXISTS public.ix_workstation_qualifications_tenant_id;
DROP INDEX IF EXISTS public.ix_working_hours_changes_user_id;
DROP INDEX IF EXISTS public.ix_working_hours_changes_tenant_id;
DROP INDEX IF EXISTS public.ix_working_hours_changes_effective_from;
DROP INDEX IF EXISTS public.ix_wh_changes_user_effective_from;
DROP INDEX IF EXISTS public.ix_vacation_requests_user_id;
DROP INDEX IF EXISTS public.ix_vacation_requests_tenant_id;
DROP INDEX IF EXISTS public.ix_vacation_requests_status;
DROP INDEX IF EXISTS public.ix_vacation_requests_date;
DROP INDEX IF EXISTS public.ix_users_tenant_id;
DROP INDEX IF EXISTS public.ix_users_email;
DROP INDEX IF EXISTS public.ix_time_entry_audit_logs_user_id;
DROP INDEX IF EXISTS public.ix_time_entry_audit_logs_time_entry_id;
DROP INDEX IF EXISTS public.ix_time_entry_audit_logs_tenant_id;
DROP INDEX IF EXISTS public.ix_time_entry_audit_logs_entry_ref;
DROP INDEX IF EXISTS public.ix_time_entry_audit_logs_changed_by;
DROP INDEX IF EXISTS public.ix_time_entries_user_id;
DROP INDEX IF EXISTS public.ix_time_entries_tenant_user_date;
DROP INDEX IF EXISTS public.ix_time_entries_tenant_id;
DROP INDEX IF EXISTS public.ix_time_entries_date;
DROP INDEX IF EXISTS public.ix_tenant_invoices_tenant_id;
DROP INDEX IF EXISTS public.ix_tenant_invoices_created_at;
DROP INDEX IF EXISTS public.ix_system_settings_tenant_id;
DROP INDEX IF EXISTS public.ix_stripe_events_tenant_id;
DROP INDEX IF EXISTS public.ix_stripe_events_processed_at;
DROP INDEX IF EXISTS public.ix_stripe_events_event_type;
DROP INDEX IF EXISTS public.ix_signup_tokens_user_id;
DROP INDEX IF EXISTS public.ix_signup_tokens_tenant_id;
DROP INDEX IF EXISTS public.ix_signup_tokens_expires_at;
DROP INDEX IF EXISTS public.ix_signup_audit_log_tenant_id;
DROP INDEX IF EXISTS public.ix_signup_audit_log_email;
DROP INDEX IF EXISTS public.ix_signup_audit_log_created_at;
DROP INDEX IF EXISTS public.ix_shift_slots_workstation_id;
DROP INDEX IF EXISTS public.ix_shift_slots_tenant_id;
DROP INDEX IF EXISTS public.ix_shift_slots_shift_plan_id;
DROP INDEX IF EXISTS public.ix_shift_slots_plan_weekday;
DROP INDEX IF EXISTS public.ix_shift_plans_tenant_id;
DROP INDEX IF EXISTS public.ix_shift_assignments_user_id;
DROP INDEX IF EXISTS public.ix_shift_assignments_tenant_id;
DROP INDEX IF EXISTS public.ix_shift_assignments_shift_slot_id;
DROP INDEX IF EXISTS public.ix_security_events_tenant_id;
DROP INDEX IF EXISTS public.ix_security_events_event;
DROP INDEX IF EXISTS public.ix_security_events_created_at;
DROP INDEX IF EXISTS public.ix_public_holidays_year;
DROP INDEX IF EXISTS public.ix_public_holidays_tenant_id;
DROP INDEX IF EXISTS public.ix_public_holidays_date;
DROP INDEX IF EXISTS public.ix_locations_tenant_id;
DROP INDEX IF EXISTS public.ix_impersonation_sessions_tenant_started;
DROP INDEX IF EXISTS public.ix_impersonation_sessions_tenant_id;
DROP INDEX IF EXISTS public.ix_impersonation_sessions_target_id;
DROP INDEX IF EXISTS public.ix_impersonation_sessions_impersonator_id;
DROP INDEX IF EXISTS public.ix_error_logs_tenant_id;
DROP INDEX IF EXISTS public.ix_error_logs_status;
DROP INDEX IF EXISTS public.ix_error_logs_level;
DROP INDEX IF EXISTS public.ix_error_logs_last_seen;
DROP INDEX IF EXISTS public.ix_error_logs_fingerprint;
DROP INDEX IF EXISTS public.ix_company_closures_tenant_id;
DROP INDEX IF EXISTS public.ix_company_closures_start_date;
DROP INDEX IF EXISTS public.ix_company_closures_end_date;
DROP INDEX IF EXISTS public.ix_change_requests_user_id;
DROP INDEX IF EXISTS public.ix_change_requests_time_entry_id;
DROP INDEX IF EXISTS public.ix_change_requests_tenant_id;
DROP INDEX IF EXISTS public.ix_change_requests_status;
DROP INDEX IF EXISTS public.ix_change_requests_proposed_reason_id;
DROP INDEX IF EXISTS public.ix_change_requests_absence_id;
DROP INDEX IF EXISTS public.ix_absences_user_id;
DROP INDEX IF EXISTS public.ix_absences_tenant_user_date;
DROP INDEX IF EXISTS public.ix_absences_tenant_id;
DROP INDEX IF EXISTS public.ix_absences_reason_id;
DROP INDEX IF EXISTS public.ix_absences_end_date;
DROP INDEX IF EXISTS public.ix_absences_date;
DROP INDEX IF EXISTS public.ix_absences_closure_id;
DROP INDEX IF EXISTS public.ix_absence_reasons_tenant_id;
ALTER TABLE IF EXISTS ONLY public.year_carryovers DROP CONSTRAINT IF EXISTS year_carryovers_pkey;
ALTER TABLE IF EXISTS ONLY public.workstations DROP CONSTRAINT IF EXISTS workstations_pkey;
ALTER TABLE IF EXISTS ONLY public.workstation_qualifications DROP CONSTRAINT IF EXISTS workstation_qualifications_pkey;
ALTER TABLE IF EXISTS ONLY public.working_hours_changes DROP CONSTRAINT IF EXISTS working_hours_changes_pkey;
ALTER TABLE IF EXISTS ONLY public.vacation_requests DROP CONSTRAINT IF EXISTS vacation_requests_pkey;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_pkey;
ALTER TABLE IF EXISTS ONLY public.tenants DROP CONSTRAINT IF EXISTS uq_tenants_stripe_subscription_id;
ALTER TABLE IF EXISTS ONLY public.tenants DROP CONSTRAINT IF EXISTS uq_tenants_stripe_customer_id;
ALTER TABLE IF EXISTS ONLY public.year_carryovers DROP CONSTRAINT IF EXISTS uq_tenant_year_carryover_user_year;
ALTER TABLE IF EXISTS ONLY public.workstations DROP CONSTRAINT IF EXISTS uq_tenant_workstation_name;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS uq_tenant_username;
ALTER TABLE IF EXISTS ONLY public.workstation_qualifications DROP CONSTRAINT IF EXISTS uq_tenant_user_workstation;
ALTER TABLE IF EXISTS ONLY public.absences DROP CONSTRAINT IF EXISTS uq_tenant_user_date_type;
ALTER TABLE IF EXISTS ONLY public.time_entries DROP CONSTRAINT IF EXISTS uq_tenant_user_date_start;
ALTER TABLE IF EXISTS ONLY public.shift_assignments DROP CONSTRAINT IF EXISTS uq_tenant_slot_user;
ALTER TABLE IF EXISTS ONLY public.shift_plans DROP CONSTRAINT IF EXISTS uq_tenant_shift_plan_name;
ALTER TABLE IF EXISTS ONLY public.locations DROP CONSTRAINT IF EXISTS uq_tenant_location_name;
ALTER TABLE IF EXISTS ONLY public.public_holidays DROP CONSTRAINT IF EXISTS uq_tenant_holiday_date;
ALTER TABLE IF EXISTS ONLY public.reduced_days DROP CONSTRAINT IF EXISTS uq_reduced_days_tenant_date;
ALTER TABLE IF EXISTS ONLY public.absence_reasons DROP CONSTRAINT IF EXISTS uq_absence_reason_tenant_name;
ALTER TABLE IF EXISTS ONLY public.time_entry_audit_logs DROP CONSTRAINT IF EXISTS time_entry_audit_logs_pkey;
ALTER TABLE IF EXISTS ONLY public.time_entries DROP CONSTRAINT IF EXISTS time_entries_pkey;
ALTER TABLE IF EXISTS ONLY public.tenants DROP CONSTRAINT IF EXISTS tenants_slug_key;
ALTER TABLE IF EXISTS ONLY public.tenants DROP CONSTRAINT IF EXISTS tenants_pkey;
ALTER TABLE IF EXISTS ONLY public.tenant_invoices DROP CONSTRAINT IF EXISTS tenant_invoices_stripe_invoice_id_key;
ALTER TABLE IF EXISTS ONLY public.tenant_invoices DROP CONSTRAINT IF EXISTS tenant_invoices_pkey;
ALTER TABLE IF EXISTS ONLY public.system_settings DROP CONSTRAINT IF EXISTS system_settings_pkey;
ALTER TABLE IF EXISTS ONLY public.stripe_events DROP CONSTRAINT IF EXISTS stripe_events_pkey;
ALTER TABLE IF EXISTS ONLY public.stripe_events DROP CONSTRAINT IF EXISTS stripe_events_event_id_key;
ALTER TABLE IF EXISTS ONLY public.signup_tokens DROP CONSTRAINT IF EXISTS signup_tokens_token_hash_key;
ALTER TABLE IF EXISTS ONLY public.signup_tokens DROP CONSTRAINT IF EXISTS signup_tokens_pkey;
ALTER TABLE IF EXISTS ONLY public.signup_audit_log DROP CONSTRAINT IF EXISTS signup_audit_log_pkey;
ALTER TABLE IF EXISTS ONLY public.shift_slots DROP CONSTRAINT IF EXISTS shift_slots_pkey;
ALTER TABLE IF EXISTS ONLY public.shift_plans DROP CONSTRAINT IF EXISTS shift_plans_pkey;
ALTER TABLE IF EXISTS ONLY public.shift_assignments DROP CONSTRAINT IF EXISTS shift_assignments_pkey;
ALTER TABLE IF EXISTS ONLY public.security_events DROP CONSTRAINT IF EXISTS security_events_pkey;
ALTER TABLE IF EXISTS ONLY public.reduced_days DROP CONSTRAINT IF EXISTS reduced_days_pkey;
ALTER TABLE IF EXISTS ONLY public.public_holidays DROP CONSTRAINT IF EXISTS public_holidays_pkey;
ALTER TABLE IF EXISTS ONLY public.locations DROP CONSTRAINT IF EXISTS locations_pkey;
ALTER TABLE IF EXISTS ONLY public.impersonation_sessions DROP CONSTRAINT IF EXISTS impersonation_sessions_pkey;
ALTER TABLE IF EXISTS ONLY public.error_logs DROP CONSTRAINT IF EXISTS error_logs_pkey;
ALTER TABLE IF EXISTS ONLY public.company_closures DROP CONSTRAINT IF EXISTS company_closures_pkey;
ALTER TABLE IF EXISTS ONLY public.change_requests DROP CONSTRAINT IF EXISTS change_requests_pkey;
ALTER TABLE IF EXISTS ONLY public.audit_log_tombstones DROP CONSTRAINT IF EXISTS audit_log_tombstones_pkey;
ALTER TABLE IF EXISTS ONLY public.audit_log_ids DROP CONSTRAINT IF EXISTS audit_log_ids_pkey;
ALTER TABLE IF EXISTS ONLY public.alembic_version DROP CONSTRAINT IF EXISTS alembic_version_pkc;
ALTER TABLE IF EXISTS ONLY public.absences DROP CONSTRAINT IF EXISTS absences_pkey;
ALTER TABLE IF EXISTS ONLY public.absence_reasons DROP CONSTRAINT IF EXISTS absence_reasons_pkey;
DROP TABLE IF EXISTS public.year_carryovers;
DROP TABLE IF EXISTS public.workstations;
DROP TABLE IF EXISTS public.workstation_qualifications;
DROP TABLE IF EXISTS public.working_hours_changes;
DROP TABLE IF EXISTS public.vacation_requests;
DROP TABLE IF EXISTS public.users;
DROP TABLE IF EXISTS public.time_entry_audit_logs;
DROP TABLE IF EXISTS public.time_entries;
DROP TABLE IF EXISTS public.tenants;
DROP TABLE IF EXISTS public.tenant_invoices;
DROP TABLE IF EXISTS public.system_settings;
DROP TABLE IF EXISTS public.stripe_events;
DROP TABLE IF EXISTS public.signup_tokens;
DROP TABLE IF EXISTS public.signup_audit_log;
DROP TABLE IF EXISTS public.shift_slots;
DROP TABLE IF EXISTS public.shift_plans;
DROP TABLE IF EXISTS public.shift_assignments;
DROP TABLE IF EXISTS public.security_events;
DROP TABLE IF EXISTS public.reduced_days;
DROP TABLE IF EXISTS public.public_holidays;
DROP TABLE IF EXISTS public.locations;
DROP TABLE IF EXISTS public.impersonation_sessions;
DROP TABLE IF EXISTS public.error_logs;
DROP TABLE IF EXISTS public.company_closures;
DROP TABLE IF EXISTS public.change_requests;
DROP TABLE IF EXISTS public.audit_log_tombstones;
DROP TABLE IF EXISTS public.audit_log_ids;
DROP TABLE IF EXISTS public.alembic_version;
DROP TABLE IF EXISTS public.absences;
DROP TABLE IF EXISTS public.absence_reasons;
DROP FUNCTION IF EXISTS public.pz_audit_tombstoned(p_id uuid);
DROP FUNCTION IF EXISTS public.pz_audit_tenant_ok(p_tenant uuid);
DROP FUNCTION IF EXISTS public.pz_audit_set_notes(p_id uuid, p_old_note text, p_new_note text, p_row_hash text);
DROP FUNCTION IF EXISTS public.pz_audit_set_head(p_tenant uuid, p_value text, p_reanchor boolean);
DROP FUNCTION IF EXISTS public.pz_audit_seal(p_ids uuid[], p_seqs bigint[], p_prevs text[], p_hashes text[]);
DROP FUNCTION IF EXISTS public.pz_audit_scrub_ok(p_old text, p_new text);
DROP FUNCTION IF EXISTS public.pz_audit_head_seq(p_tenant uuid);
DROP FUNCTION IF EXISTS public.pz_audit_head_guard();
DROP FUNCTION IF EXISTS public.pz_audit_guard();
DROP FUNCTION IF EXISTS public.pz_audit_delete(p_ids uuid[]);
DROP FUNCTION IF EXISTS public.pz_audit_claim_id(p_id uuid, p_tenant uuid);
DROP TYPE IF EXISTS public.userrole;
DROP TYPE IF EXISTS public.changerequesttype;
DROP TYPE IF EXISTS public.changerequeststatus;
DROP TYPE IF EXISTS public.absencetype;
--
-- Name: absencetype; Type: TYPE; Schema: public; Owner: praxiszeit
--

CREATE TYPE public.absencetype AS ENUM (
    'VACATION',
    'SICK',
    'TRAINING',
    'OTHER',
    'OVERTIME',
    'PAID_LEAVE'
);


ALTER TYPE public.absencetype OWNER TO praxiszeit;

--
-- Name: changerequeststatus; Type: TYPE; Schema: public; Owner: praxiszeit
--

CREATE TYPE public.changerequeststatus AS ENUM (
    'pending',
    'approved',
    'rejected'
);


ALTER TYPE public.changerequeststatus OWNER TO praxiszeit;

--
-- Name: changerequesttype; Type: TYPE; Schema: public; Owner: praxiszeit
--

CREATE TYPE public.changerequesttype AS ENUM (
    'create',
    'update',
    'delete'
);


ALTER TYPE public.changerequesttype OWNER TO praxiszeit;

--
-- Name: userrole; Type: TYPE; Schema: public; Owner: praxiszeit
--

CREATE TYPE public.userrole AS ENUM (
    'ADMIN',
    'EMPLOYEE'
);


ALTER TYPE public.userrole OWNER TO praxiszeit;

--
-- Name: pz_audit_claim_id(uuid, uuid); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_claim_id(p_id uuid, p_tenant uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
BEGIN
    IF pg_trigger_depth() < 1 THEN
        RAISE EXCEPTION 'pz_audit_claim_id: nur ueber den Protokoll-Trigger'
            USING ERRCODE = '42501';
    END IF;
    INSERT INTO audit_log_ids (id, tenant_id) VALUES (p_id, p_tenant)
        ON CONFLICT (id) DO NOTHING;
    RETURN FOUND;
END $$;


ALTER FUNCTION public.pz_audit_claim_id(p_id uuid, p_tenant uuid) OWNER TO praxiszeit;

--
-- Name: pz_audit_delete(uuid[]); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_delete(p_ids uuid[]) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
DECLARE
    n integer;
BEGIN
    IF EXISTS (SELECT 1 FROM time_entry_audit_logs
                WHERE id = ANY(p_ids) AND chain_seq IS NULL) THEN
        RAISE EXCEPTION 'pz_audit_delete: nur versiegelte Zeilen duerfen geloescht werden';
    END IF;
    IF EXISTS (SELECT 1 FROM time_entry_audit_logs t
                WHERE t.id = ANY(p_ids)
                  AND (pz_audit_head_seq(t.tenant_id) IS NULL
                       OR t.chain_seq > pz_audit_head_seq(t.tenant_id))) THEN
        RAISE EXCEPTION 'pz_audit_delete: nur Zeilen bis zum gesiegelten Kettenende duerfen geloescht werden';
    END IF;
    -- Jede geloeschte id bekommt einen Grabstein: pz_audit_guard laesst sie
    -- nie wieder einfuegen (Review-Runde 3).
    WITH d AS (
        DELETE FROM time_entry_audit_logs t
         WHERE t.id = ANY(p_ids)
           AND pz_audit_tenant_ok(t.tenant_id)
        RETURNING t.id, t.tenant_id
    ), g AS (
        INSERT INTO audit_log_tombstones (id, tenant_id)
        SELECT d.id, d.tenant_id FROM d
        ON CONFLICT (id) DO NOTHING
    )
    SELECT count(*) INTO n FROM d;
    RETURN n;
END $$;


ALTER FUNCTION public.pz_audit_delete(p_ids uuid[]) OWNER TO praxiszeit;

--
-- Name: pz_audit_guard(); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    tbl_owner oid;
BEGIN
    SELECT relowner INTO tbl_owner FROM pg_class WHERE oid = TG_RELID;
    IF pg_has_role(current_user, tbl_owner, 'MEMBER')
       OR COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false) THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        IF TG_OP = 'INSERT' THEN
            -- auch Zeilen der Eigentuemerin bekommen ihre id fest vergeben
            PERFORM pz_audit_claim_id(NEW.id, NEW.tenant_id);
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'INSERT' THEN
        -- Review-Runde 3: eine geloeschte Zeile kehrt nie zurueck. Sonst liesse
        -- sich eine echte Zeile (gueltiger row_hash, er bindet die id) nach
        -- pz_audit_delete Byte fuer Byte wieder einfuegen — etwa ein alter
        -- Vermerk "Kettenende neu gesetzt", der pz_audit_set_head ein
        -- Zuruecksetzen erlaubt, oder eine nach Art. 17 entfernte Zeile.
        IF pz_audit_tombstoned(NEW.id) THEN
            RAISE EXCEPTION 'time_entry_audit_logs: geloeschte Zeile % darf nicht zurueckkehren', NEW.id
                USING ERRCODE = '42501';
        END IF;
        -- Review-Runde 5: der Grabstein allein ist ein Blick auf den Stand bei
        -- Beginn dieser Anweisung - ein paralleles pz_audit_delete derselben id
        -- (noch nicht festgeschrieben) sieht er nicht, das Einfuegen wartete nur
        -- am Primaerschluessel und gelaenge nach dessen Commit. Die id-Vergabe
        -- haengt am Primaerschluessel von audit_log_ids: eine schon (auch
        -- parallel) vergebene id scheitert hier, ohne Fenster.
        IF NOT pz_audit_claim_id(NEW.id, NEW.tenant_id) THEN
            RAISE EXCEPTION 'time_entry_audit_logs: Zeilen-id % war schon vergeben, eine geloeschte Zeile darf nicht zurueckkehren', NEW.id
                USING ERRCODE = '42501';
        END IF;
        -- created_at steht in der Pruefsumme: eine kopierte alte Zeile traegt
        -- ihren alten Zeitpunkt und faellt hier heraus. Spielraum fuer lange
        -- Transaktionen und Uhrabweichung zwischen App und Datenbank.
        IF NEW.created_at IS NULL
           OR NEW.created_at < transaction_timestamp() - interval '10 minutes'
           OR NEW.created_at > clock_timestamp() + interval '10 minutes' THEN
            RAISE EXCEPTION 'time_entry_audit_logs: Anlagezeitpunkt % liegt nicht in der Gegenwart', NEW.created_at
                USING ERRCODE = '42501';
        END IF;
        IF NEW.row_hash IS NULL OR NEW.hash_version IS NULL THEN
            RAISE EXCEPTION 'time_entry_audit_logs: Zeile ohne Pruefsumme abgelehnt'
                USING ERRCODE = '42501';
        END IF;
        IF NEW.chain_seq IS NOT NULL OR NEW.chain_prev IS NOT NULL OR NEW.chain_hash IS NOT NULL THEN
            RAISE EXCEPTION 'time_entry_audit_logs: Kettenglied nur ueber pz_audit_seal'
                USING ERRCODE = '42501';
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'time_entry_audit_logs: % nur ueber die Protokollfunktionen erlaubt', TG_OP
        USING ERRCODE = '42501';
END $$;


ALTER FUNCTION public.pz_audit_guard() OWNER TO praxiszeit;

--
-- Name: pz_audit_head_guard(); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_head_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    tbl_owner oid;
    hit boolean := false;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        hit := OLD.key IN ('audit_chain_head', 'audit_legacy_cutoff');
    END IF;
    IF TG_OP <> 'DELETE' AND NOT hit THEN
        hit := NEW.key IN ('audit_chain_head', 'audit_legacy_cutoff');
    END IF;
    IF NOT hit THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    SELECT relowner INTO tbl_owner FROM pg_class WHERE oid = TG_RELID;
    IF pg_has_role(current_user, tbl_owner, 'MEMBER')
       OR COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false) THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'system_settings: Kettenende/Altbestandsgrenze des Aenderungsprotokolls (%) nur ueber die Protokollfunktionen', TG_OP
        USING ERRCODE = '42501';
END $$;


ALTER FUNCTION public.pz_audit_head_guard() OWNER TO praxiszeit;

--
-- Name: pz_audit_head_seq(uuid); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_head_seq(p_tenant uuid) RETURNS bigint
    LANGUAGE sql STABLE
    SET search_path TO 'public', 'pg_temp'
    AS $_$
    SELECT CASE WHEN value ~ '^[0-9]{1,18}:[0-9a-f]*:[0-9a-f]+$'
                THEN split_part(value, ':', 1)::bigint ELSE -1 END
      FROM system_settings
     WHERE key = 'audit_chain_head' AND tenant_id = p_tenant
$_$;


ALTER FUNCTION public.pz_audit_head_seq(p_tenant uuid) OWNER TO praxiszeit;

--
-- Name: pz_audit_scrub_ok(text, text); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_scrub_ok(p_old text, p_new text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'public', 'pg_temp'
    AS $$
DECLARE
    parts text[];
    n integer;
    pos integer;
    k integer;
    seg text;
    hit integer;
BEGIN
    IF p_new IS NULL OR p_new IS NOT DISTINCT FROM p_old THEN
        RETURN true;
    END IF;
    IF p_old IS NULL THEN
        RETURN false;
    END IF;
    parts := regexp_split_to_array(p_new, '\[anonymisiert\]|deleted_[0-9a-f]{8}');
    n := array_length(parts, 1);
    IF n < 2 OR left(p_old, length(parts[1])) <> parts[1] THEN
        RETURN false;
    END IF;
    pos := length(parts[1]) + 1;          -- erstes noch nicht zugeordnetes Zeichen
    FOR k IN 2 .. n - 1 LOOP
        seg := parts[k];
        IF seg = '' THEN
            pos := pos + 1;
            CONTINUE;
        END IF;
        hit := strpos(substr(p_old, pos + 1), seg);
        IF hit = 0 THEN
            RETURN false;
        END IF;
        pos := pos + hit + length(seg);
    END LOOP;
    RETURN length(p_old) - length(parts[n]) >= pos
       AND right(p_old, length(parts[n])) = parts[n];
END $$;


ALTER FUNCTION public.pz_audit_scrub_ok(p_old text, p_new text) OWNER TO praxiszeit;

--
-- Name: pz_audit_seal(uuid[], bigint[], text[], text[]); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_seal(p_ids uuid[], p_seqs bigint[], p_prevs text[], p_hashes text[]) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
DECLARE
    n integer;
    v_cnt integer := COALESCE(array_length(p_ids, 1), 0);
    v_tenant uuid;
    v_head bigint;
    v_start bigint;
BEGIN
    IF v_cnt = 0 THEN
        RETURN 0;
    END IF;
    IF COALESCE(array_length(p_seqs, 1), 0) <> v_cnt OR COALESCE(array_length(p_prevs, 1), 0) <> v_cnt
       OR COALESCE(array_length(p_hashes, 1), 0) <> v_cnt THEN
        RAISE EXCEPTION 'pz_audit_seal: Listen ungleich lang';
    END IF;
    IF (SELECT count(DISTINCT tenant_id) FROM time_entry_audit_logs WHERE id = ANY(p_ids)) <> 1 THEN
        RAISE EXCEPTION 'pz_audit_seal: Zeilen genau eines Mandanten erwartet';
    END IF;
    SELECT tenant_id INTO v_tenant FROM time_entry_audit_logs WHERE id = ANY(p_ids) LIMIT 1;
    IF NOT pz_audit_tenant_ok(v_tenant) THEN
        RAISE EXCEPTION 'pz_audit_seal: fremder Mandant';
    END IF;
    v_head := pz_audit_head_seq(v_tenant);
    IF v_head < 0 THEN
        RAISE EXCEPTION 'pz_audit_seal: Kettenende zerstoert';
    END IF;
    SELECT GREATEST(COALESCE(max(chain_seq), 0), COALESCE(v_head, 0)) + 1 INTO v_start
      FROM time_entry_audit_logs WHERE tenant_id = v_tenant;
    IF EXISTS (SELECT 1 FROM unnest(p_seqs) WITH ORDINALITY AS u(s, i)
                WHERE u.s IS DISTINCT FROM v_start + u.i - 1) THEN
        RAISE EXCEPTION 'pz_audit_seal: Kettenglieder muessen lueckenlos bei % anschliessen', v_start;
    END IF;
    UPDATE time_entry_audit_logs t
       SET chain_seq = s.seq, chain_prev = s.prev, chain_hash = s.h
      FROM unnest(p_ids, p_seqs, p_prevs, p_hashes) AS s(id, seq, prev, h)
     WHERE t.id = s.id
       AND t.chain_seq IS NULL
       AND t.tenant_id = v_tenant;
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> v_cnt THEN
        RAISE EXCEPTION 'pz_audit_seal: % von % Zeilen versiegelt', n, v_cnt;
    END IF;
    RETURN n;
END $$;


ALTER FUNCTION public.pz_audit_seal(p_ids uuid[], p_seqs bigint[], p_prevs text[], p_hashes text[]) OWNER TO praxiszeit;

--
-- Name: pz_audit_set_head(uuid, text, boolean); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_set_head(p_tenant uuid, p_value text, p_reanchor boolean) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $_$
DECLARE
    v_seq bigint;
    v_hash text;
    v_top bigint;
    v_top_hash text;
    v_old text;
    v_old_seq bigint;
BEGIN
    IF NOT pz_audit_tenant_ok(p_tenant) THEN
        RAISE EXCEPTION 'pz_audit_set_head: fremder Mandant';
    END IF;
    IF p_value IS NULL OR p_value !~ '^[0-9]{1,18}:[0-9a-f]*:[0-9a-f]+$' THEN
        RAISE EXCEPTION 'pz_audit_set_head: ungueltiger Wert';
    END IF;
    v_seq := split_part(p_value, ':', 1)::bigint;
    v_hash := split_part(p_value, ':', 2);
    SELECT chain_seq, COALESCE(chain_hash, '') INTO v_top, v_top_hash
      FROM time_entry_audit_logs
     WHERE tenant_id = p_tenant AND chain_seq IS NOT NULL
     ORDER BY chain_seq DESC LIMIT 1;
    IF v_seq <> COALESCE(v_top, 0) OR v_hash <> COALESCE(v_top_hash, '') THEN
        RAISE EXCEPTION 'pz_audit_set_head: Kettenende nur auf das hoechste versiegelte Glied (%)',
            COALESCE(v_top, 0) USING ERRCODE = '42501';
    END IF;
    SELECT value INTO v_old FROM system_settings
     WHERE key = 'audit_chain_head' AND tenant_id = p_tenant
       FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO system_settings (key, tenant_id, value, description)
        VALUES ('audit_chain_head', p_tenant, p_value,
                'Aenderungsprotokoll: letztes Kettenglied (#537)');
        RETURN;
    END IF;
    IF v_old ~ '^[0-9]{1,18}:[0-9a-f]*:[0-9a-f]+$' THEN
        v_old_seq := split_part(v_old, ':', 1)::bigint;
        IF v_seq < v_old_seq AND NOT (
            p_reanchor AND EXISTS (
                SELECT 1 FROM time_entry_audit_logs
                 WHERE tenant_id = p_tenant AND chain_seq IS NULL
                   AND action = 'audit_chain_reanchored' AND row_hash IS NOT NULL
                   -- nur ein Vermerk aus DIESEM Vorgang (Review-Runde 3): ein
                   -- alter, wieder eingefuegter Vermerk oeffnete sonst das
                   -- Zuruecksetzen beliebig oft
                   AND created_at >= transaction_timestamp() - interval '1 minute')) THEN
            RAISE EXCEPTION 'pz_audit_set_head: Kettenende darf nicht zurueckgesetzt werden (% -> %)',
                v_old_seq, v_seq USING ERRCODE = '42501';
        END IF;
    END IF;
    UPDATE system_settings SET value = p_value, updated_at = now()
     WHERE key = 'audit_chain_head' AND tenant_id = p_tenant;
END $_$;


ALTER FUNCTION public.pz_audit_set_head(p_tenant uuid, p_value text, p_reanchor boolean) OWNER TO praxiszeit;

--
-- Name: pz_audit_set_notes(uuid, text, text, text); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_set_notes(p_id uuid, p_old_note text, p_new_note text, p_row_hash text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
DECLARE
    r record;
BEGIN
    SELECT t.old_note, t.new_note, t.row_hash INTO r
      FROM time_entry_audit_logs t
     WHERE t.id = p_id
       AND pz_audit_tenant_ok(t.tenant_id)
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'pz_audit_set_notes: Zeile % nicht gefunden', p_id;
    END IF;
    IF (r.row_hash IS NULL) <> (p_row_hash IS NULL) THEN
        RAISE EXCEPTION 'pz_audit_set_notes: Pruefsumme darf weder entfernt noch neu gesetzt werden'
            USING ERRCODE = '42501';
    END IF;
    IF NOT pz_audit_scrub_ok(r.old_note, p_old_note) OR NOT pz_audit_scrub_ok(r.new_note, p_new_note) THEN
        RAISE EXCEPTION 'pz_audit_set_notes: Notizen nur leeren oder durch Anonymisierung ersetzen'
            USING ERRCODE = '42501';
    END IF;
    UPDATE time_entry_audit_logs t
       SET old_note = p_old_note, new_note = p_new_note, row_hash = p_row_hash
     WHERE t.id = p_id;
END $$;


ALTER FUNCTION public.pz_audit_set_notes(p_id uuid, p_old_note text, p_new_note text, p_row_hash text) OWNER TO praxiszeit;

--
-- Name: pz_audit_tenant_ok(uuid); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_tenant_ok(p_tenant uuid) RETURNS boolean
    LANGUAGE sql STABLE
    AS $$
    SELECT current_setting('app.is_superadmin', true) = 'true'
        OR p_tenant = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = session_user), false)
$$;


ALTER FUNCTION public.pz_audit_tenant_ok(p_tenant uuid) OWNER TO praxiszeit;

--
-- Name: pz_audit_tombstoned(uuid); Type: FUNCTION; Schema: public; Owner: praxiszeit
--

CREATE FUNCTION public.pz_audit_tombstoned(p_id uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
    SELECT EXISTS (SELECT 1 FROM audit_log_tombstones WHERE id = p_id)
$$;


ALTER FUNCTION public.pz_audit_tombstoned(p_id uuid) OWNER TO praxiszeit;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: absence_reasons; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.absence_reasons (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(80) NOT NULL,
    color character varying(7),
    base_behavior character varying(20) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tracks_child_sick_limit boolean DEFAULT false NOT NULL
);

ALTER TABLE ONLY public.absence_reasons FORCE ROW LEVEL SECURITY;


ALTER TABLE public.absence_reasons OWNER TO praxiszeit;

--
-- Name: absences; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.absences (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    date date NOT NULL,
    type public.absencetype NOT NULL,
    hours numeric(4,2) NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    end_date date,
    tenant_id uuid NOT NULL,
    start_time time without time zone,
    end_time time without time zone,
    closure_id uuid,
    half_day boolean,
    reason_id uuid,
    raw_hours numeric(4,2)
);

ALTER TABLE ONLY public.absences FORCE ROW LEVEL SECURITY;


ALTER TABLE public.absences OWNER TO praxiszeit;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO praxiszeit;

--
-- Name: audit_log_ids; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.audit_log_ids (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL
);


ALTER TABLE public.audit_log_ids OWNER TO praxiszeit;

--
-- Name: audit_log_tombstones; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.audit_log_tombstones (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    deleted_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.audit_log_tombstones OWNER TO praxiszeit;

--
-- Name: change_requests; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.change_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    request_type public.changerequesttype NOT NULL,
    status public.changerequeststatus DEFAULT 'pending'::public.changerequeststatus NOT NULL,
    time_entry_id uuid,
    proposed_date date,
    proposed_start_time time without time zone,
    proposed_end_time time without time zone,
    proposed_break_minutes integer,
    proposed_note text,
    original_date date,
    original_start_time time without time zone,
    original_end_time time without time zone,
    original_break_minutes integer,
    original_note text,
    reason text NOT NULL,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    rejection_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    entry_kind character varying(20) DEFAULT 'time_entry'::character varying NOT NULL,
    absence_id uuid,
    proposed_absence_type character varying(20),
    proposed_absence_hours numeric(4,2),
    original_absence_type character varying(20),
    original_absence_hours numeric(4,2),
    break_waiver_reason text,
    proposed_reason_id uuid,
    proposed_sunday_exception_reason text,
    request_credit_override boolean DEFAULT false NOT NULL,
    original_uncredited_minutes integer
);

ALTER TABLE ONLY public.change_requests FORCE ROW LEVEL SECURITY;


ALTER TABLE public.change_requests OWNER TO praxiszeit;

--
-- Name: company_closures; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.company_closures (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(255) NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    counts_as_vacation boolean DEFAULT true NOT NULL
);

ALTER TABLE ONLY public.company_closures FORCE ROW LEVEL SECURITY;


ALTER TABLE public.company_closures OWNER TO praxiszeit;

--
-- Name: COLUMN company_closures.name; Type: COMMENT; Schema: public; Owner: praxiszeit
--

COMMENT ON COLUMN public.company_closures.name IS 'Description, e.g. Betriebsferien Sommer 2026';


--
-- Name: error_logs; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.error_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    level character varying(20) NOT NULL,
    logger character varying(200) NOT NULL,
    message text NOT NULL,
    traceback text,
    path character varying(500),
    method character varying(10),
    status_code integer,
    user_id uuid,
    fingerprint character varying(64) NOT NULL,
    count integer DEFAULT 1 NOT NULL,
    first_seen timestamp with time zone DEFAULT now() NOT NULL,
    last_seen timestamp with time zone DEFAULT now() NOT NULL,
    status character varying(20) DEFAULT '''open'''::character varying NOT NULL,
    resolved_at timestamp with time zone,
    resolved_by uuid,
    github_issue_url character varying(500),
    tenant_id uuid
);

ALTER TABLE ONLY public.error_logs FORCE ROW LEVEL SECURITY;


ALTER TABLE public.error_logs OWNER TO praxiszeit;

--
-- Name: impersonation_sessions; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.impersonation_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    impersonator_id uuid NOT NULL,
    target_id uuid NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    ended_at timestamp with time zone
);

ALTER TABLE ONLY public.impersonation_sessions FORCE ROW LEVEL SECURITY;


ALTER TABLE public.impersonation_sessions OWNER TO praxiszeit;

--
-- Name: locations; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.locations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.locations FORCE ROW LEVEL SECURITY;


ALTER TABLE public.locations OWNER TO praxiszeit;

--
-- Name: public_holidays; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.public_holidays (
    id uuid NOT NULL,
    date date NOT NULL,
    name character varying(255) NOT NULL,
    year integer NOT NULL,
    tenant_id uuid NOT NULL,
    is_custom boolean DEFAULT false NOT NULL,
    source character varying(20) DEFAULT 'workalendar'::character varying NOT NULL
);

ALTER TABLE ONLY public.public_holidays FORCE ROW LEVEL SECURITY;


ALTER TABLE public.public_holidays OWNER TO praxiszeit;

--
-- Name: reduced_days; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.reduced_days (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    date date NOT NULL,
    label character varying(100) NOT NULL,
    max_hours numeric(4,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by uuid
);

ALTER TABLE ONLY public.reduced_days FORCE ROW LEVEL SECURITY;


ALTER TABLE public.reduced_days OWNER TO praxiszeit;

--
-- Name: security_events; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.security_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid,
    event character varying(50) NOT NULL,
    subject_user_id uuid,
    actor character varying(200) NOT NULL,
    detail text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.security_events FORCE ROW LEVEL SECURITY;


ALTER TABLE public.security_events OWNER TO praxiszeit;

--
-- Name: shift_assignments; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.shift_assignments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    shift_slot_id uuid NOT NULL,
    user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.shift_assignments FORCE ROW LEVEL SECURITY;


ALTER TABLE public.shift_assignments OWNER TO praxiszeit;

--
-- Name: shift_plans; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.shift_plans (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    is_active boolean DEFAULT false NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    active_from_date date,
    active_until_date date,
    visible_to_employees boolean DEFAULT false NOT NULL
);

ALTER TABLE ONLY public.shift_plans FORCE ROW LEVEL SECURITY;


ALTER TABLE public.shift_plans OWNER TO praxiszeit;

--
-- Name: shift_slots; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.shift_slots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    shift_plan_id uuid NOT NULL,
    workstation_id uuid NOT NULL,
    weekday smallint NOT NULL,
    start_time time without time zone NOT NULL,
    end_time time without time zone NOT NULL,
    min_staff smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    note text
);

ALTER TABLE ONLY public.shift_slots FORCE ROW LEVEL SECURITY;


ALTER TABLE public.shift_slots OWNER TO praxiszeit;

--
-- Name: signup_audit_log; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.signup_audit_log (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid,
    email character varying(255) NOT NULL,
    event character varying(30) NOT NULL,
    ip_address character varying(45),
    user_agent character varying(500),
    accepted_terms boolean,
    accepted_privacy boolean,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.signup_audit_log FORCE ROW LEVEL SECURITY;


ALTER TABLE public.signup_audit_log OWNER TO praxiszeit;

--
-- Name: signup_tokens; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.signup_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(128) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.signup_tokens FORCE ROW LEVEL SECURITY;


ALTER TABLE public.signup_tokens OWNER TO praxiszeit;

--
-- Name: stripe_events; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.stripe_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    event_id character varying(255) NOT NULL,
    event_type character varying(100) NOT NULL,
    processed_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    payload_excerpt text
);

ALTER TABLE ONLY public.stripe_events FORCE ROW LEVEL SECURITY;


ALTER TABLE public.stripe_events OWNER TO praxiszeit;

--
-- Name: system_settings; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.system_settings (
    key character varying(100) NOT NULL,
    value text NOT NULL,
    description text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.system_settings FORCE ROW LEVEL SECURITY;


ALTER TABLE public.system_settings OWNER TO praxiszeit;

--
-- Name: tenant_invoices; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.tenant_invoices (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    stripe_invoice_id character varying(255) NOT NULL,
    amount_cents integer NOT NULL,
    currency character varying(3) DEFAULT 'eur'::character varying NOT NULL,
    status character varying(20) NOT NULL,
    paid_at timestamp with time zone,
    period_start timestamp with time zone,
    period_end timestamp with time zone,
    hosted_invoice_url text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.tenant_invoices FORCE ROW LEVEL SECURITY;


ALTER TABLE public.tenant_invoices OWNER TO praxiszeit;

--
-- Name: tenants; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.tenants (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(100) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    mode character varying(20) DEFAULT 'multi'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    plan character varying(20) DEFAULT 'trial'::character varying NOT NULL,
    subscription_status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    trial_ends_at timestamp with time zone,
    seat_limit integer,
    stripe_customer_id character varying(255),
    stripe_subscription_id character varying(255),
    billing_email character varying(255),
    company_name character varying(255),
    vat_id character varying(50),
    country character varying(2),
    billing_address jsonb,
    scheduled_suspend_at timestamp with time zone,
    scheduled_suspend_by uuid,
    deletion_requested_at timestamp with time zone,
    deletion_requested_by uuid,
    anonymized_at timestamp with time zone
);

ALTER TABLE ONLY public.tenants FORCE ROW LEVEL SECURITY;


ALTER TABLE public.tenants OWNER TO praxiszeit;

--
-- Name: time_entries; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.time_entries (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    date date NOT NULL,
    start_time time without time zone NOT NULL,
    end_time time without time zone,
    break_minutes integer NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    sunday_exception_reason text,
    tenant_id uuid NOT NULL,
    break_waiver_reason text,
    raw_start_time time without time zone,
    raw_end_time time without time zone,
    uncredited_minutes integer DEFAULT 0 NOT NULL,
    credit_override boolean DEFAULT false NOT NULL,
    auto_closed boolean DEFAULT false NOT NULL,
    clamp_grace_minutes integer
);

ALTER TABLE ONLY public.time_entries FORCE ROW LEVEL SECURITY;


ALTER TABLE public.time_entries OWNER TO praxiszeit;

--
-- Name: time_entry_audit_logs; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.time_entry_audit_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    time_entry_id uuid,
    user_id uuid NOT NULL,
    changed_by uuid,
    action character varying(40) NOT NULL,
    old_date date,
    old_start_time time without time zone,
    old_end_time time without time zone,
    old_break_minutes integer,
    old_note text,
    new_date date,
    new_start_time time without time zone,
    new_end_time time without time zone,
    new_break_minutes integer,
    new_note text,
    source character varying(40) DEFAULT 'manual'::character varying NOT NULL,
    change_request_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    row_hash character varying(64),
    entry_ref uuid,
    changed_by_ref uuid,
    change_request_ref uuid,
    hash_version smallint,
    old_raw_start_time time without time zone,
    old_raw_end_time time without time zone,
    old_presence_end_time time without time zone,
    old_uncredited_minutes integer,
    new_raw_start_time time without time zone,
    new_raw_end_time time without time zone,
    new_presence_end_time time without time zone,
    new_uncredited_minutes integer,
    chain_seq bigint,
    chain_prev character varying(64),
    chain_hash character varying(64)
);

ALTER TABLE ONLY public.time_entry_audit_logs FORCE ROW LEVEL SECURITY;


ALTER TABLE public.time_entry_audit_logs OWNER TO praxiszeit;

--
-- Name: users; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    email character varying(255),
    password_hash character varying(255) NOT NULL,
    first_name character varying(100) NOT NULL,
    last_name character varying(100) NOT NULL,
    role public.userrole NOT NULL,
    weekly_hours numeric(4,2) NOT NULL,
    vacation_days numeric(4,1) NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    track_hours boolean DEFAULT true NOT NULL,
    calendar_color character varying(7) DEFAULT '#93C5FD'::character varying NOT NULL,
    work_days_per_week integer DEFAULT 5 NOT NULL,
    username character varying(100) NOT NULL,
    vacation_carryover_deadline date,
    use_daily_schedule boolean DEFAULT false NOT NULL,
    hours_monday numeric(4,2),
    hours_tuesday numeric(4,2),
    hours_wednesday numeric(4,2),
    hours_thursday numeric(4,2),
    hours_friday numeric(4,2),
    is_hidden boolean DEFAULT false NOT NULL,
    token_version integer DEFAULT 0 NOT NULL,
    exempt_from_arbzg boolean DEFAULT false NOT NULL,
    is_night_worker boolean DEFAULT false NOT NULL,
    totp_secret character varying(255),
    totp_enabled boolean DEFAULT false NOT NULL,
    deactivated_at timestamp with time zone,
    first_work_day date,
    last_work_day date,
    profile_picture text,
    tenant_id uuid,
    last_totp_counter bigint,
    onboarding_completed_at timestamp with time zone,
    department character varying(100),
    receives_company_closures boolean DEFAULT true NOT NULL,
    child_sick_days_per_year integer,
    milog_working_time_account boolean DEFAULT false NOT NULL,
    agreed_monthly_hours numeric(5,1),
    use_fixed_monthly_target boolean DEFAULT false NOT NULL,
    work_blocks jsonb
);

ALTER TABLE ONLY public.users FORCE ROW LEVEL SECURITY;


ALTER TABLE public.users OWNER TO praxiszeit;

--
-- Name: COLUMN users.vacation_carryover_deadline; Type: COMMENT; Schema: public; Owner: praxiszeit
--

COMMENT ON COLUMN public.users.vacation_carryover_deadline IS 'Individual deadline for vacation carryover. NULL = default (March 31 of next year)';


--
-- Name: vacation_requests; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.vacation_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    date date NOT NULL,
    end_date date,
    hours numeric(5,2) NOT NULL,
    note text,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    rejection_reason text,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    absence_type character varying(20) DEFAULT 'vacation'::character varying NOT NULL,
    last_modified_by uuid,
    last_modified_at timestamp with time zone,
    half_day boolean DEFAULT false NOT NULL
);

ALTER TABLE ONLY public.vacation_requests FORCE ROW LEVEL SECURITY;


ALTER TABLE public.vacation_requests OWNER TO praxiszeit;

--
-- Name: working_hours_changes; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.working_hours_changes (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    effective_from date NOT NULL,
    weekly_hours numeric(4,2) NOT NULL,
    note character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    use_daily_schedule boolean DEFAULT false NOT NULL,
    hours_monday numeric(4,2),
    hours_tuesday numeric(4,2),
    hours_wednesday numeric(4,2),
    hours_thursday numeric(4,2),
    hours_friday numeric(4,2),
    work_days_per_week integer,
    blocks jsonb,
    vacation_days numeric(4,1) NOT NULL,
    track_hours boolean NOT NULL,
    milog_working_time_account boolean NOT NULL,
    agreed_monthly_hours numeric(5,1),
    use_fixed_monthly_target boolean NOT NULL
);

ALTER TABLE ONLY public.working_hours_changes FORCE ROW LEVEL SECURITY;


ALTER TABLE public.working_hours_changes OWNER TO praxiszeit;

--
-- Name: workstation_qualifications; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.workstation_qualifications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    workstation_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.workstation_qualifications FORCE ROW LEVEL SECURITY;


ALTER TABLE public.workstation_qualifications OWNER TO praxiszeit;

--
-- Name: workstations; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.workstations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    location_id uuid,
    name character varying(255) NOT NULL,
    color character varying(7),
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.workstations FORCE ROW LEVEL SECURITY;


ALTER TABLE public.workstations OWNER TO praxiszeit;

--
-- Name: year_carryovers; Type: TABLE; Schema: public; Owner: praxiszeit
--

CREATE TABLE public.year_carryovers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    year integer NOT NULL,
    overtime_hours numeric(8,2) DEFAULT '0'::numeric NOT NULL,
    vacation_days numeric(5,2) DEFAULT '0'::numeric NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    source character varying(20) DEFAULT 'year_closing'::character varying NOT NULL
);

ALTER TABLE ONLY public.year_carryovers FORCE ROW LEVEL SECURITY;


ALTER TABLE public.year_carryovers OWNER TO praxiszeit;

--
-- Data for Name: absence_reasons; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.absence_reasons (id, tenant_id, name, color, base_behavior, is_active, sort_order, created_at, tracks_child_sick_limit) FROM stdin;
\.


--
-- Data for Name: absences; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.absences (id, user_id, date, type, hours, note, created_at, end_date, tenant_id, start_time, end_time, closure_id, half_day, reason_id, raw_hours) FROM stdin;
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.alembic_version (version_num) FROM stdin;
076_audit_chain
\.


--
-- Data for Name: audit_log_ids; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.audit_log_ids (id, tenant_id) FROM stdin;
\.


--
-- Data for Name: audit_log_tombstones; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.audit_log_tombstones (id, tenant_id, deleted_at) FROM stdin;
\.


--
-- Data for Name: change_requests; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.change_requests (id, user_id, request_type, status, time_entry_id, proposed_date, proposed_start_time, proposed_end_time, proposed_break_minutes, proposed_note, original_date, original_start_time, original_end_time, original_break_minutes, original_note, reason, reviewed_by, reviewed_at, rejection_reason, created_at, updated_at, tenant_id, entry_kind, absence_id, proposed_absence_type, proposed_absence_hours, original_absence_type, original_absence_hours, break_waiver_reason, proposed_reason_id, proposed_sunday_exception_reason, request_credit_override, original_uncredited_minutes) FROM stdin;
\.


--
-- Data for Name: company_closures; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.company_closures (id, name, start_date, end_date, created_by, created_at, updated_at, tenant_id, counts_as_vacation) FROM stdin;
\.


--
-- Data for Name: error_logs; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.error_logs (id, level, logger, message, traceback, path, method, status_code, user_id, fingerprint, count, first_seen, last_seen, status, resolved_at, resolved_by, github_issue_url, tenant_id) FROM stdin;
\.


--
-- Data for Name: impersonation_sessions; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.impersonation_sessions (id, tenant_id, impersonator_id, target_id, started_at, ended_at) FROM stdin;
\.


--
-- Data for Name: locations; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.locations (id, tenant_id, name, sort_order, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: public_holidays; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.public_holidays (id, date, name, year, tenant_id, is_custom, source) FROM stdin;
\.


--
-- Data for Name: reduced_days; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.reduced_days (id, tenant_id, date, label, max_hours, created_at, created_by) FROM stdin;
\.


--
-- Data for Name: security_events; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.security_events (id, tenant_id, event, subject_user_id, actor, detail, created_at) FROM stdin;
\.


--
-- Data for Name: shift_assignments; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.shift_assignments (id, tenant_id, shift_slot_id, user_id, created_at) FROM stdin;
\.


--
-- Data for Name: shift_plans; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.shift_plans (id, tenant_id, name, description, is_active, created_by, created_at, updated_at, active_from_date, active_until_date, visible_to_employees) FROM stdin;
\.


--
-- Data for Name: shift_slots; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.shift_slots (id, tenant_id, shift_plan_id, workstation_id, weekday, start_time, end_time, min_staff, created_at, updated_at, note) FROM stdin;
\.


--
-- Data for Name: signup_audit_log; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.signup_audit_log (id, tenant_id, email, event, ip_address, user_agent, accepted_terms, accepted_privacy, created_at) FROM stdin;
\.


--
-- Data for Name: signup_tokens; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.signup_tokens (id, tenant_id, user_id, token_hash, expires_at, consumed_at, created_at) FROM stdin;
\.


--
-- Data for Name: stripe_events; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.stripe_events (id, event_id, event_type, processed_at, tenant_id, payload_excerpt) FROM stdin;
\.


--
-- Data for Name: system_settings; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.system_settings (key, value, description, updated_at, tenant_id) FROM stdin;
\.


--
-- Data for Name: tenant_invoices; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.tenant_invoices (id, tenant_id, stripe_invoice_id, amount_cents, currency, status, paid_at, period_start, period_end, hosted_invoice_url, created_at) FROM stdin;
\.


--
-- Data for Name: tenants; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.tenants (id, name, slug, is_active, mode, created_at, plan, subscription_status, trial_ends_at, seat_limit, stripe_customer_id, stripe_subscription_id, billing_email, company_name, vat_id, country, billing_address, scheduled_suspend_at, scheduled_suspend_by, deletion_requested_at, deletion_requested_by, anonymized_at) FROM stdin;
\.


--
-- Data for Name: time_entries; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.time_entries (id, user_id, date, start_time, end_time, break_minutes, note, created_at, updated_at, sunday_exception_reason, tenant_id, break_waiver_reason, raw_start_time, raw_end_time, uncredited_minutes, credit_override, auto_closed, clamp_grace_minutes) FROM stdin;
\.


--
-- Data for Name: time_entry_audit_logs; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.time_entry_audit_logs (id, time_entry_id, user_id, changed_by, action, old_date, old_start_time, old_end_time, old_break_minutes, old_note, new_date, new_start_time, new_end_time, new_break_minutes, new_note, source, change_request_id, created_at, tenant_id, row_hash, entry_ref, changed_by_ref, change_request_ref, hash_version, old_raw_start_time, old_raw_end_time, old_presence_end_time, old_uncredited_minutes, new_raw_start_time, new_raw_end_time, new_presence_end_time, new_uncredited_minutes, chain_seq, chain_prev, chain_hash) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.users (id, email, password_hash, first_name, last_name, role, weekly_hours, vacation_days, is_active, created_at, updated_at, track_hours, calendar_color, work_days_per_week, username, vacation_carryover_deadline, use_daily_schedule, hours_monday, hours_tuesday, hours_wednesday, hours_thursday, hours_friday, is_hidden, token_version, exempt_from_arbzg, is_night_worker, totp_secret, totp_enabled, deactivated_at, first_work_day, last_work_day, profile_picture, tenant_id, last_totp_counter, onboarding_completed_at, department, receives_company_closures, child_sick_days_per_year, milog_working_time_account, agreed_monthly_hours, use_fixed_monthly_target, work_blocks) FROM stdin;
\.


--
-- Data for Name: vacation_requests; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.vacation_requests (id, user_id, date, end_date, hours, note, status, rejection_reason, reviewed_by, reviewed_at, created_at, updated_at, tenant_id, absence_type, last_modified_by, last_modified_at, half_day) FROM stdin;
\.


--
-- Data for Name: working_hours_changes; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.working_hours_changes (id, user_id, effective_from, weekly_hours, note, created_at, tenant_id, use_daily_schedule, hours_monday, hours_tuesday, hours_wednesday, hours_thursday, hours_friday, work_days_per_week, blocks, vacation_days, track_hours, milog_working_time_account, agreed_monthly_hours, use_fixed_monthly_target) FROM stdin;
\.


--
-- Data for Name: workstation_qualifications; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.workstation_qualifications (id, tenant_id, user_id, workstation_id, created_at) FROM stdin;
\.


--
-- Data for Name: workstations; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.workstations (id, tenant_id, location_id, name, color, sort_order, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: year_carryovers; Type: TABLE DATA; Schema: public; Owner: praxiszeit
--

COPY public.year_carryovers (id, user_id, year, overtime_hours, vacation_days, created_at, updated_at, tenant_id, source) FROM stdin;
\.


--
-- Name: absence_reasons absence_reasons_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.absence_reasons
    ADD CONSTRAINT absence_reasons_pkey PRIMARY KEY (id);


--
-- Name: absences absences_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.absences
    ADD CONSTRAINT absences_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audit_log_ids audit_log_ids_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.audit_log_ids
    ADD CONSTRAINT audit_log_ids_pkey PRIMARY KEY (id);


--
-- Name: audit_log_tombstones audit_log_tombstones_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.audit_log_tombstones
    ADD CONSTRAINT audit_log_tombstones_pkey PRIMARY KEY (id);


--
-- Name: change_requests change_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.change_requests
    ADD CONSTRAINT change_requests_pkey PRIMARY KEY (id);


--
-- Name: company_closures company_closures_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.company_closures
    ADD CONSTRAINT company_closures_pkey PRIMARY KEY (id);


--
-- Name: error_logs error_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.error_logs
    ADD CONSTRAINT error_logs_pkey PRIMARY KEY (id);


--
-- Name: impersonation_sessions impersonation_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.impersonation_sessions
    ADD CONSTRAINT impersonation_sessions_pkey PRIMARY KEY (id);


--
-- Name: locations locations_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT locations_pkey PRIMARY KEY (id);


--
-- Name: public_holidays public_holidays_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.public_holidays
    ADD CONSTRAINT public_holidays_pkey PRIMARY KEY (id);


--
-- Name: reduced_days reduced_days_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.reduced_days
    ADD CONSTRAINT reduced_days_pkey PRIMARY KEY (id);


--
-- Name: security_events security_events_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.security_events
    ADD CONSTRAINT security_events_pkey PRIMARY KEY (id);


--
-- Name: shift_assignments shift_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_assignments
    ADD CONSTRAINT shift_assignments_pkey PRIMARY KEY (id);


--
-- Name: shift_plans shift_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_plans
    ADD CONSTRAINT shift_plans_pkey PRIMARY KEY (id);


--
-- Name: shift_slots shift_slots_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_slots
    ADD CONSTRAINT shift_slots_pkey PRIMARY KEY (id);


--
-- Name: signup_audit_log signup_audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.signup_audit_log
    ADD CONSTRAINT signup_audit_log_pkey PRIMARY KEY (id);


--
-- Name: signup_tokens signup_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.signup_tokens
    ADD CONSTRAINT signup_tokens_pkey PRIMARY KEY (id);


--
-- Name: signup_tokens signup_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.signup_tokens
    ADD CONSTRAINT signup_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: stripe_events stripe_events_event_id_key; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.stripe_events
    ADD CONSTRAINT stripe_events_event_id_key UNIQUE (event_id);


--
-- Name: stripe_events stripe_events_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.stripe_events
    ADD CONSTRAINT stripe_events_pkey PRIMARY KEY (id);


--
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (key, tenant_id);


--
-- Name: tenant_invoices tenant_invoices_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.tenant_invoices
    ADD CONSTRAINT tenant_invoices_pkey PRIMARY KEY (id);


--
-- Name: tenant_invoices tenant_invoices_stripe_invoice_id_key; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.tenant_invoices
    ADD CONSTRAINT tenant_invoices_stripe_invoice_id_key UNIQUE (stripe_invoice_id);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_slug_key; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_slug_key UNIQUE (slug);


--
-- Name: time_entries time_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.time_entries
    ADD CONSTRAINT time_entries_pkey PRIMARY KEY (id);


--
-- Name: time_entry_audit_logs time_entry_audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.time_entry_audit_logs
    ADD CONSTRAINT time_entry_audit_logs_pkey PRIMARY KEY (id);


--
-- Name: absence_reasons uq_absence_reason_tenant_name; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.absence_reasons
    ADD CONSTRAINT uq_absence_reason_tenant_name UNIQUE (tenant_id, name);


--
-- Name: reduced_days uq_reduced_days_tenant_date; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.reduced_days
    ADD CONSTRAINT uq_reduced_days_tenant_date UNIQUE (tenant_id, date);


--
-- Name: public_holidays uq_tenant_holiday_date; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.public_holidays
    ADD CONSTRAINT uq_tenant_holiday_date UNIQUE (tenant_id, date);


--
-- Name: locations uq_tenant_location_name; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT uq_tenant_location_name UNIQUE (tenant_id, name);


--
-- Name: shift_plans uq_tenant_shift_plan_name; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_plans
    ADD CONSTRAINT uq_tenant_shift_plan_name UNIQUE (tenant_id, name);


--
-- Name: shift_assignments uq_tenant_slot_user; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_assignments
    ADD CONSTRAINT uq_tenant_slot_user UNIQUE (tenant_id, shift_slot_id, user_id);


--
-- Name: time_entries uq_tenant_user_date_start; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.time_entries
    ADD CONSTRAINT uq_tenant_user_date_start UNIQUE (tenant_id, user_id, date, start_time);


--
-- Name: absences uq_tenant_user_date_type; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.absences
    ADD CONSTRAINT uq_tenant_user_date_type UNIQUE (tenant_id, user_id, date, type);


--
-- Name: workstation_qualifications uq_tenant_user_workstation; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.workstation_qualifications
    ADD CONSTRAINT uq_tenant_user_workstation UNIQUE (tenant_id, user_id, workstation_id);


--
-- Name: users uq_tenant_username; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_tenant_username UNIQUE (tenant_id, username);


--
-- Name: workstations uq_tenant_workstation_name; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.workstations
    ADD CONSTRAINT uq_tenant_workstation_name UNIQUE (tenant_id, name);


--
-- Name: year_carryovers uq_tenant_year_carryover_user_year; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.year_carryovers
    ADD CONSTRAINT uq_tenant_year_carryover_user_year UNIQUE (tenant_id, user_id, year);


--
-- Name: tenants uq_tenants_stripe_customer_id; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT uq_tenants_stripe_customer_id UNIQUE (stripe_customer_id);


--
-- Name: tenants uq_tenants_stripe_subscription_id; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT uq_tenants_stripe_subscription_id UNIQUE (stripe_subscription_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: vacation_requests vacation_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.vacation_requests
    ADD CONSTRAINT vacation_requests_pkey PRIMARY KEY (id);


--
-- Name: working_hours_changes working_hours_changes_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.working_hours_changes
    ADD CONSTRAINT working_hours_changes_pkey PRIMARY KEY (id);


--
-- Name: workstation_qualifications workstation_qualifications_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.workstation_qualifications
    ADD CONSTRAINT workstation_qualifications_pkey PRIMARY KEY (id);


--
-- Name: workstations workstations_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.workstations
    ADD CONSTRAINT workstations_pkey PRIMARY KEY (id);


--
-- Name: year_carryovers year_carryovers_pkey; Type: CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.year_carryovers
    ADD CONSTRAINT year_carryovers_pkey PRIMARY KEY (id);


--
-- Name: ix_absence_reasons_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_absence_reasons_tenant_id ON public.absence_reasons USING btree (tenant_id);


--
-- Name: ix_absences_closure_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_absences_closure_id ON public.absences USING btree (closure_id);


--
-- Name: ix_absences_date; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_absences_date ON public.absences USING btree (date);


--
-- Name: ix_absences_end_date; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_absences_end_date ON public.absences USING btree (end_date);


--
-- Name: ix_absences_reason_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_absences_reason_id ON public.absences USING btree (reason_id);


--
-- Name: ix_absences_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_absences_tenant_id ON public.absences USING btree (tenant_id);


--
-- Name: ix_absences_tenant_user_date; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_absences_tenant_user_date ON public.absences USING btree (tenant_id, user_id, date);


--
-- Name: ix_absences_user_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_absences_user_id ON public.absences USING btree (user_id);


--
-- Name: ix_change_requests_absence_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_change_requests_absence_id ON public.change_requests USING btree (absence_id);


--
-- Name: ix_change_requests_proposed_reason_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_change_requests_proposed_reason_id ON public.change_requests USING btree (proposed_reason_id);


--
-- Name: ix_change_requests_status; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_change_requests_status ON public.change_requests USING btree (status);


--
-- Name: ix_change_requests_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_change_requests_tenant_id ON public.change_requests USING btree (tenant_id);


--
-- Name: ix_change_requests_time_entry_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_change_requests_time_entry_id ON public.change_requests USING btree (time_entry_id);


--
-- Name: ix_change_requests_user_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_change_requests_user_id ON public.change_requests USING btree (user_id);


--
-- Name: ix_company_closures_end_date; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_company_closures_end_date ON public.company_closures USING btree (end_date);


--
-- Name: ix_company_closures_start_date; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_company_closures_start_date ON public.company_closures USING btree (start_date);


--
-- Name: ix_company_closures_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_company_closures_tenant_id ON public.company_closures USING btree (tenant_id);


--
-- Name: ix_error_logs_fingerprint; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_error_logs_fingerprint ON public.error_logs USING btree (fingerprint);


--
-- Name: ix_error_logs_last_seen; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_error_logs_last_seen ON public.error_logs USING btree (last_seen);


--
-- Name: ix_error_logs_level; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_error_logs_level ON public.error_logs USING btree (level);


--
-- Name: ix_error_logs_status; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_error_logs_status ON public.error_logs USING btree (status);


--
-- Name: ix_error_logs_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_error_logs_tenant_id ON public.error_logs USING btree (tenant_id);


--
-- Name: ix_impersonation_sessions_impersonator_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_impersonation_sessions_impersonator_id ON public.impersonation_sessions USING btree (impersonator_id);


--
-- Name: ix_impersonation_sessions_target_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_impersonation_sessions_target_id ON public.impersonation_sessions USING btree (target_id);


--
-- Name: ix_impersonation_sessions_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_impersonation_sessions_tenant_id ON public.impersonation_sessions USING btree (tenant_id);


--
-- Name: ix_impersonation_sessions_tenant_started; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_impersonation_sessions_tenant_started ON public.impersonation_sessions USING btree (tenant_id, started_at);


--
-- Name: ix_locations_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_locations_tenant_id ON public.locations USING btree (tenant_id);


--
-- Name: ix_public_holidays_date; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_public_holidays_date ON public.public_holidays USING btree (date);


--
-- Name: ix_public_holidays_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_public_holidays_tenant_id ON public.public_holidays USING btree (tenant_id);


--
-- Name: ix_public_holidays_year; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_public_holidays_year ON public.public_holidays USING btree (year);


--
-- Name: ix_security_events_created_at; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_security_events_created_at ON public.security_events USING btree (created_at);


--
-- Name: ix_security_events_event; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_security_events_event ON public.security_events USING btree (event);


--
-- Name: ix_security_events_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_security_events_tenant_id ON public.security_events USING btree (tenant_id);


--
-- Name: ix_shift_assignments_shift_slot_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_shift_assignments_shift_slot_id ON public.shift_assignments USING btree (shift_slot_id);


--
-- Name: ix_shift_assignments_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_shift_assignments_tenant_id ON public.shift_assignments USING btree (tenant_id);


--
-- Name: ix_shift_assignments_user_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_shift_assignments_user_id ON public.shift_assignments USING btree (user_id);


--
-- Name: ix_shift_plans_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_shift_plans_tenant_id ON public.shift_plans USING btree (tenant_id);


--
-- Name: ix_shift_slots_plan_weekday; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_shift_slots_plan_weekday ON public.shift_slots USING btree (tenant_id, shift_plan_id, weekday);


--
-- Name: ix_shift_slots_shift_plan_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_shift_slots_shift_plan_id ON public.shift_slots USING btree (shift_plan_id);


--
-- Name: ix_shift_slots_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_shift_slots_tenant_id ON public.shift_slots USING btree (tenant_id);


--
-- Name: ix_shift_slots_workstation_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_shift_slots_workstation_id ON public.shift_slots USING btree (workstation_id);


--
-- Name: ix_signup_audit_log_created_at; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_signup_audit_log_created_at ON public.signup_audit_log USING btree (created_at);


--
-- Name: ix_signup_audit_log_email; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_signup_audit_log_email ON public.signup_audit_log USING btree (email);


--
-- Name: ix_signup_audit_log_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_signup_audit_log_tenant_id ON public.signup_audit_log USING btree (tenant_id);


--
-- Name: ix_signup_tokens_expires_at; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_signup_tokens_expires_at ON public.signup_tokens USING btree (expires_at);


--
-- Name: ix_signup_tokens_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_signup_tokens_tenant_id ON public.signup_tokens USING btree (tenant_id);


--
-- Name: ix_signup_tokens_user_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_signup_tokens_user_id ON public.signup_tokens USING btree (user_id);


--
-- Name: ix_stripe_events_event_type; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_stripe_events_event_type ON public.stripe_events USING btree (event_type);


--
-- Name: ix_stripe_events_processed_at; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_stripe_events_processed_at ON public.stripe_events USING btree (processed_at);


--
-- Name: ix_stripe_events_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_stripe_events_tenant_id ON public.stripe_events USING btree (tenant_id);


--
-- Name: ix_system_settings_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_system_settings_tenant_id ON public.system_settings USING btree (tenant_id);


--
-- Name: ix_tenant_invoices_created_at; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_tenant_invoices_created_at ON public.tenant_invoices USING btree (created_at);


--
-- Name: ix_tenant_invoices_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_tenant_invoices_tenant_id ON public.tenant_invoices USING btree (tenant_id);


--
-- Name: ix_time_entries_date; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_time_entries_date ON public.time_entries USING btree (date);


--
-- Name: ix_time_entries_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_time_entries_tenant_id ON public.time_entries USING btree (tenant_id);


--
-- Name: ix_time_entries_tenant_user_date; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_time_entries_tenant_user_date ON public.time_entries USING btree (tenant_id, user_id, date);


--
-- Name: ix_time_entries_user_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_time_entries_user_id ON public.time_entries USING btree (user_id);


--
-- Name: ix_time_entry_audit_logs_changed_by; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_time_entry_audit_logs_changed_by ON public.time_entry_audit_logs USING btree (changed_by);


--
-- Name: ix_time_entry_audit_logs_entry_ref; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_time_entry_audit_logs_entry_ref ON public.time_entry_audit_logs USING btree (entry_ref);


--
-- Name: ix_time_entry_audit_logs_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_time_entry_audit_logs_tenant_id ON public.time_entry_audit_logs USING btree (tenant_id);


--
-- Name: ix_time_entry_audit_logs_time_entry_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_time_entry_audit_logs_time_entry_id ON public.time_entry_audit_logs USING btree (time_entry_id);


--
-- Name: ix_time_entry_audit_logs_user_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_time_entry_audit_logs_user_id ON public.time_entry_audit_logs USING btree (user_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_users_tenant_id ON public.users USING btree (tenant_id);


--
-- Name: ix_vacation_requests_date; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_vacation_requests_date ON public.vacation_requests USING btree (date);


--
-- Name: ix_vacation_requests_status; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_vacation_requests_status ON public.vacation_requests USING btree (status);


--
-- Name: ix_vacation_requests_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_vacation_requests_tenant_id ON public.vacation_requests USING btree (tenant_id);


--
-- Name: ix_vacation_requests_user_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_vacation_requests_user_id ON public.vacation_requests USING btree (user_id);


--
-- Name: ix_wh_changes_user_effective_from; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_wh_changes_user_effective_from ON public.working_hours_changes USING btree (user_id, effective_from);


--
-- Name: ix_working_hours_changes_effective_from; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_working_hours_changes_effective_from ON public.working_hours_changes USING btree (effective_from);


--
-- Name: ix_working_hours_changes_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_working_hours_changes_tenant_id ON public.working_hours_changes USING btree (tenant_id);


--
-- Name: ix_working_hours_changes_user_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_working_hours_changes_user_id ON public.working_hours_changes USING btree (user_id);


--
-- Name: ix_workstation_qualifications_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_workstation_qualifications_tenant_id ON public.workstation_qualifications USING btree (tenant_id);


--
-- Name: ix_workstation_qualifications_user_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_workstation_qualifications_user_id ON public.workstation_qualifications USING btree (user_id);


--
-- Name: ix_workstation_qualifications_workstation_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_workstation_qualifications_workstation_id ON public.workstation_qualifications USING btree (workstation_id);


--
-- Name: ix_workstations_location_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_workstations_location_id ON public.workstations USING btree (location_id);


--
-- Name: ix_workstations_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_workstations_tenant_id ON public.workstations USING btree (tenant_id);


--
-- Name: ix_year_carryovers_tenant_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_year_carryovers_tenant_id ON public.year_carryovers USING btree (tenant_id);


--
-- Name: ix_year_carryovers_user_id; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE INDEX ix_year_carryovers_user_id ON public.year_carryovers USING btree (user_id);


--
-- Name: uq_audit_tenant_chain_seq; Type: INDEX; Schema: public; Owner: praxiszeit
--

CREATE UNIQUE INDEX uq_audit_tenant_chain_seq ON public.time_entry_audit_logs USING btree (tenant_id, chain_seq);


--
-- Name: time_entry_audit_logs pz_audit_guard_write; Type: TRIGGER; Schema: public; Owner: praxiszeit
--

CREATE TRIGGER pz_audit_guard_write BEFORE INSERT OR DELETE OR UPDATE ON public.time_entry_audit_logs FOR EACH ROW EXECUTE FUNCTION public.pz_audit_guard();


--
-- Name: system_settings pz_audit_head_guard_write; Type: TRIGGER; Schema: public; Owner: praxiszeit
--

CREATE TRIGGER pz_audit_head_guard_write BEFORE INSERT OR DELETE OR UPDATE ON public.system_settings FOR EACH ROW EXECUTE FUNCTION public.pz_audit_head_guard();


--
-- Name: absence_reasons absence_reasons_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.absence_reasons
    ADD CONSTRAINT absence_reasons_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: absences absences_reason_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.absences
    ADD CONSTRAINT absences_reason_id_fkey FOREIGN KEY (reason_id) REFERENCES public.absence_reasons(id) ON DELETE SET NULL;


--
-- Name: absences absences_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.absences
    ADD CONSTRAINT absences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: audit_log_ids audit_log_ids_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.audit_log_ids
    ADD CONSTRAINT audit_log_ids_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: audit_log_tombstones audit_log_tombstones_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.audit_log_tombstones
    ADD CONSTRAINT audit_log_tombstones_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: change_requests change_requests_proposed_reason_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.change_requests
    ADD CONSTRAINT change_requests_proposed_reason_id_fkey FOREIGN KEY (proposed_reason_id) REFERENCES public.absence_reasons(id) ON DELETE SET NULL;


--
-- Name: change_requests change_requests_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.change_requests
    ADD CONSTRAINT change_requests_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: change_requests change_requests_time_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.change_requests
    ADD CONSTRAINT change_requests_time_entry_id_fkey FOREIGN KEY (time_entry_id) REFERENCES public.time_entries(id) ON DELETE SET NULL;


--
-- Name: change_requests change_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.change_requests
    ADD CONSTRAINT change_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: company_closures company_closures_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.company_closures
    ADD CONSTRAINT company_closures_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: error_logs error_logs_resolved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.error_logs
    ADD CONSTRAINT error_logs_resolved_by_fkey FOREIGN KEY (resolved_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: error_logs error_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.error_logs
    ADD CONSTRAINT error_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: absences fk_absences_closure_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.absences
    ADD CONSTRAINT fk_absences_closure_id FOREIGN KEY (closure_id) REFERENCES public.company_closures(id) ON DELETE SET NULL;


--
-- Name: absences fk_absences_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.absences
    ADD CONSTRAINT fk_absences_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: change_requests fk_change_requests_absence_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.change_requests
    ADD CONSTRAINT fk_change_requests_absence_id FOREIGN KEY (absence_id) REFERENCES public.absences(id) ON DELETE SET NULL;


--
-- Name: change_requests fk_change_requests_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.change_requests
    ADD CONSTRAINT fk_change_requests_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: company_closures fk_company_closures_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.company_closures
    ADD CONSTRAINT fk_company_closures_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: error_logs fk_error_logs_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.error_logs
    ADD CONSTRAINT fk_error_logs_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: public_holidays fk_public_holidays_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.public_holidays
    ADD CONSTRAINT fk_public_holidays_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: signup_tokens fk_signup_tokens_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.signup_tokens
    ADD CONSTRAINT fk_signup_tokens_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: signup_tokens fk_signup_tokens_user_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.signup_tokens
    ADD CONSTRAINT fk_signup_tokens_user_id FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: system_settings fk_system_settings_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT fk_system_settings_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: tenant_invoices fk_tenant_invoices_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.tenant_invoices
    ADD CONSTRAINT fk_tenant_invoices_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: time_entries fk_time_entries_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.time_entries
    ADD CONSTRAINT fk_time_entries_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: time_entry_audit_logs fk_time_entry_audit_logs_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.time_entry_audit_logs
    ADD CONSTRAINT fk_time_entry_audit_logs_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: users fk_users_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: vacation_requests fk_vacation_requests_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.vacation_requests
    ADD CONSTRAINT fk_vacation_requests_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: working_hours_changes fk_working_hours_changes_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.working_hours_changes
    ADD CONSTRAINT fk_working_hours_changes_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: year_carryovers fk_year_carryovers_tenant_id; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.year_carryovers
    ADD CONSTRAINT fk_year_carryovers_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: impersonation_sessions impersonation_sessions_impersonator_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.impersonation_sessions
    ADD CONSTRAINT impersonation_sessions_impersonator_id_fkey FOREIGN KEY (impersonator_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: impersonation_sessions impersonation_sessions_target_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.impersonation_sessions
    ADD CONSTRAINT impersonation_sessions_target_id_fkey FOREIGN KEY (target_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: impersonation_sessions impersonation_sessions_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.impersonation_sessions
    ADD CONSTRAINT impersonation_sessions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: locations locations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT locations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: reduced_days reduced_days_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.reduced_days
    ADD CONSTRAINT reduced_days_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: reduced_days reduced_days_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.reduced_days
    ADD CONSTRAINT reduced_days_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: security_events security_events_subject_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.security_events
    ADD CONSTRAINT security_events_subject_user_id_fkey FOREIGN KEY (subject_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: security_events security_events_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.security_events
    ADD CONSTRAINT security_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: shift_assignments shift_assignments_shift_slot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_assignments
    ADD CONSTRAINT shift_assignments_shift_slot_id_fkey FOREIGN KEY (shift_slot_id) REFERENCES public.shift_slots(id) ON DELETE CASCADE;


--
-- Name: shift_assignments shift_assignments_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_assignments
    ADD CONSTRAINT shift_assignments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: shift_assignments shift_assignments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_assignments
    ADD CONSTRAINT shift_assignments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: shift_plans shift_plans_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_plans
    ADD CONSTRAINT shift_plans_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: shift_plans shift_plans_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_plans
    ADD CONSTRAINT shift_plans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: shift_slots shift_slots_shift_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_slots
    ADD CONSTRAINT shift_slots_shift_plan_id_fkey FOREIGN KEY (shift_plan_id) REFERENCES public.shift_plans(id) ON DELETE CASCADE;


--
-- Name: shift_slots shift_slots_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_slots
    ADD CONSTRAINT shift_slots_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: shift_slots shift_slots_workstation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.shift_slots
    ADD CONSTRAINT shift_slots_workstation_id_fkey FOREIGN KEY (workstation_id) REFERENCES public.workstations(id) ON DELETE RESTRICT;


--
-- Name: time_entries time_entries_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.time_entries
    ADD CONSTRAINT time_entries_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: time_entry_audit_logs time_entry_audit_logs_change_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.time_entry_audit_logs
    ADD CONSTRAINT time_entry_audit_logs_change_request_id_fkey FOREIGN KEY (change_request_id) REFERENCES public.change_requests(id) ON DELETE SET NULL;


--
-- Name: time_entry_audit_logs time_entry_audit_logs_changed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.time_entry_audit_logs
    ADD CONSTRAINT time_entry_audit_logs_changed_by_fkey FOREIGN KEY (changed_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: time_entry_audit_logs time_entry_audit_logs_time_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.time_entry_audit_logs
    ADD CONSTRAINT time_entry_audit_logs_time_entry_id_fkey FOREIGN KEY (time_entry_id) REFERENCES public.time_entries(id) ON DELETE SET NULL;


--
-- Name: time_entry_audit_logs time_entry_audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.time_entry_audit_logs
    ADD CONSTRAINT time_entry_audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: vacation_requests vacation_requests_last_modified_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.vacation_requests
    ADD CONSTRAINT vacation_requests_last_modified_by_fkey FOREIGN KEY (last_modified_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: vacation_requests vacation_requests_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.vacation_requests
    ADD CONSTRAINT vacation_requests_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: vacation_requests vacation_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.vacation_requests
    ADD CONSTRAINT vacation_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: working_hours_changes working_hours_changes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.working_hours_changes
    ADD CONSTRAINT working_hours_changes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: workstation_qualifications workstation_qualifications_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.workstation_qualifications
    ADD CONSTRAINT workstation_qualifications_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: workstation_qualifications workstation_qualifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.workstation_qualifications
    ADD CONSTRAINT workstation_qualifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: workstation_qualifications workstation_qualifications_workstation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.workstation_qualifications
    ADD CONSTRAINT workstation_qualifications_workstation_id_fkey FOREIGN KEY (workstation_id) REFERENCES public.workstations(id) ON DELETE CASCADE;


--
-- Name: workstations workstations_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.workstations
    ADD CONSTRAINT workstations_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.locations(id) ON DELETE RESTRICT;


--
-- Name: workstations workstations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.workstations
    ADD CONSTRAINT workstations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: year_carryovers year_carryovers_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: praxiszeit
--

ALTER TABLE ONLY public.year_carryovers
    ADD CONSTRAINT year_carryovers_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: absence_reasons; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.absence_reasons ENABLE ROW LEVEL SECURITY;

--
-- Name: absences; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.absences ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_log_ids; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.audit_log_ids ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_log_tombstones; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.audit_log_tombstones ENABLE ROW LEVEL SECURITY;

--
-- Name: change_requests; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.change_requests ENABLE ROW LEVEL SECURITY;

--
-- Name: company_closures; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.company_closures ENABLE ROW LEVEL SECURITY;

--
-- Name: error_logs; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.error_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: impersonation_sessions; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.impersonation_sessions ENABLE ROW LEVEL SECURITY;

--
-- Name: locations; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.locations ENABLE ROW LEVEL SECURITY;

--
-- Name: public_holidays; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.public_holidays ENABLE ROW LEVEL SECURITY;

--
-- Name: reduced_days; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.reduced_days ENABLE ROW LEVEL SECURITY;

--
-- Name: security_events; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.security_events ENABLE ROW LEVEL SECURITY;

--
-- Name: shift_assignments; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.shift_assignments ENABLE ROW LEVEL SECURITY;

--
-- Name: shift_plans; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.shift_plans ENABLE ROW LEVEL SECURITY;

--
-- Name: shift_slots; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.shift_slots ENABLE ROW LEVEL SECURITY;

--
-- Name: signup_audit_log; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.signup_audit_log ENABLE ROW LEVEL SECURITY;

--
-- Name: signup_tokens; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.signup_tokens ENABLE ROW LEVEL SECURITY;

--
-- Name: stripe_events; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.stripe_events ENABLE ROW LEVEL SECURITY;

--
-- Name: system_settings; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;

--
-- Name: tenant_invoices; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.tenant_invoices ENABLE ROW LEVEL SECURITY;

--
-- Name: absence_reasons tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.absence_reasons USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: absences tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.absences USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: audit_log_ids tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.audit_log_ids USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: audit_log_tombstones tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.audit_log_tombstones USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: change_requests tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.change_requests USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: company_closures tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.company_closures USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: error_logs tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.error_logs USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) OR (tenant_id IS NULL))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) OR (tenant_id IS NULL)));


--
-- Name: impersonation_sessions tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.impersonation_sessions USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: locations tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.locations USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: public_holidays tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.public_holidays USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: reduced_days tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.reduced_days USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: security_events tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.security_events USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: shift_assignments tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.shift_assignments USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: shift_plans tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.shift_plans USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: shift_slots tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.shift_slots USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: signup_audit_log tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.signup_audit_log USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: signup_tokens tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.signup_tokens USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: stripe_events tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.stripe_events USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: system_settings tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.system_settings USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: tenant_invoices tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.tenant_invoices USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: tenants tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.tenants USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: time_entries tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.time_entries USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: time_entry_audit_logs tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.time_entry_audit_logs USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: users tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.users USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) OR (tenant_id IS NULL))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) OR (tenant_id IS NULL)));


--
-- Name: vacation_requests tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.vacation_requests USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: working_hours_changes tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.working_hours_changes USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: workstation_qualifications tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.workstation_qualifications USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: workstations tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.workstations USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: year_carryovers tenant_isolation; Type: POLICY; Schema: public; Owner: praxiszeit
--

CREATE POLICY tenant_isolation ON public.year_carryovers USING (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))) WITH CHECK (((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: tenants; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;

--
-- Name: time_entries; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.time_entries ENABLE ROW LEVEL SECURITY;

--
-- Name: time_entry_audit_logs; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.time_entry_audit_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: users; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

--
-- Name: vacation_requests; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.vacation_requests ENABLE ROW LEVEL SECURITY;

--
-- Name: working_hours_changes; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.working_hours_changes ENABLE ROW LEVEL SECURITY;

--
-- Name: workstation_qualifications; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.workstation_qualifications ENABLE ROW LEVEL SECURITY;

--
-- Name: workstations; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.workstations ENABLE ROW LEVEL SECURITY;

--
-- Name: year_carryovers; Type: ROW SECURITY; Schema: public; Owner: praxiszeit
--

ALTER TABLE public.year_carryovers ENABLE ROW LEVEL SECURITY;

--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner
--

GRANT USAGE ON SCHEMA public TO praxiszeit_app;


--
-- Name: FUNCTION pz_audit_claim_id(p_id uuid, p_tenant uuid); Type: ACL; Schema: public; Owner: praxiszeit
--

REVOKE ALL ON FUNCTION public.pz_audit_claim_id(p_id uuid, p_tenant uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION public.pz_audit_claim_id(p_id uuid, p_tenant uuid) TO praxiszeit_app;


--
-- Name: FUNCTION pz_audit_delete(p_ids uuid[]); Type: ACL; Schema: public; Owner: praxiszeit
--

REVOKE ALL ON FUNCTION public.pz_audit_delete(p_ids uuid[]) FROM PUBLIC;
GRANT ALL ON FUNCTION public.pz_audit_delete(p_ids uuid[]) TO praxiszeit_app;


--
-- Name: FUNCTION pz_audit_head_seq(p_tenant uuid); Type: ACL; Schema: public; Owner: praxiszeit
--

REVOKE ALL ON FUNCTION public.pz_audit_head_seq(p_tenant uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION public.pz_audit_head_seq(p_tenant uuid) TO praxiszeit_app;


--
-- Name: FUNCTION pz_audit_scrub_ok(p_old text, p_new text); Type: ACL; Schema: public; Owner: praxiszeit
--

REVOKE ALL ON FUNCTION public.pz_audit_scrub_ok(p_old text, p_new text) FROM PUBLIC;
GRANT ALL ON FUNCTION public.pz_audit_scrub_ok(p_old text, p_new text) TO praxiszeit_app;


--
-- Name: FUNCTION pz_audit_seal(p_ids uuid[], p_seqs bigint[], p_prevs text[], p_hashes text[]); Type: ACL; Schema: public; Owner: praxiszeit
--

REVOKE ALL ON FUNCTION public.pz_audit_seal(p_ids uuid[], p_seqs bigint[], p_prevs text[], p_hashes text[]) FROM PUBLIC;
GRANT ALL ON FUNCTION public.pz_audit_seal(p_ids uuid[], p_seqs bigint[], p_prevs text[], p_hashes text[]) TO praxiszeit_app;


--
-- Name: FUNCTION pz_audit_set_head(p_tenant uuid, p_value text, p_reanchor boolean); Type: ACL; Schema: public; Owner: praxiszeit
--

REVOKE ALL ON FUNCTION public.pz_audit_set_head(p_tenant uuid, p_value text, p_reanchor boolean) FROM PUBLIC;
GRANT ALL ON FUNCTION public.pz_audit_set_head(p_tenant uuid, p_value text, p_reanchor boolean) TO praxiszeit_app;


--
-- Name: FUNCTION pz_audit_set_notes(p_id uuid, p_old_note text, p_new_note text, p_row_hash text); Type: ACL; Schema: public; Owner: praxiszeit
--

REVOKE ALL ON FUNCTION public.pz_audit_set_notes(p_id uuid, p_old_note text, p_new_note text, p_row_hash text) FROM PUBLIC;
GRANT ALL ON FUNCTION public.pz_audit_set_notes(p_id uuid, p_old_note text, p_new_note text, p_row_hash text) TO praxiszeit_app;


--
-- Name: FUNCTION pz_audit_tenant_ok(p_tenant uuid); Type: ACL; Schema: public; Owner: praxiszeit
--

REVOKE ALL ON FUNCTION public.pz_audit_tenant_ok(p_tenant uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION public.pz_audit_tenant_ok(p_tenant uuid) TO praxiszeit_app;


--
-- Name: FUNCTION pz_audit_tombstoned(p_id uuid); Type: ACL; Schema: public; Owner: praxiszeit
--

REVOKE ALL ON FUNCTION public.pz_audit_tombstoned(p_id uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION public.pz_audit_tombstoned(p_id uuid) TO praxiszeit_app;


--
-- Name: TABLE absence_reasons; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.absence_reasons TO praxiszeit_app;


--
-- Name: TABLE absences; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.absences TO praxiszeit_app;


--
-- Name: TABLE alembic_version; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.alembic_version TO praxiszeit_app;


--
-- Name: TABLE change_requests; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.change_requests TO praxiszeit_app;


--
-- Name: TABLE company_closures; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.company_closures TO praxiszeit_app;


--
-- Name: TABLE error_logs; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.error_logs TO praxiszeit_app;


--
-- Name: TABLE impersonation_sessions; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.impersonation_sessions TO praxiszeit_app;


--
-- Name: TABLE locations; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.locations TO praxiszeit_app;


--
-- Name: TABLE public_holidays; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.public_holidays TO praxiszeit_app;


--
-- Name: TABLE reduced_days; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.reduced_days TO praxiszeit_app;


--
-- Name: TABLE security_events; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.security_events TO praxiszeit_app;


--
-- Name: TABLE shift_assignments; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.shift_assignments TO praxiszeit_app;


--
-- Name: TABLE shift_plans; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.shift_plans TO praxiszeit_app;


--
-- Name: TABLE shift_slots; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.shift_slots TO praxiszeit_app;


--
-- Name: TABLE signup_audit_log; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.signup_audit_log TO praxiszeit_app;


--
-- Name: TABLE signup_tokens; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.signup_tokens TO praxiszeit_app;


--
-- Name: TABLE stripe_events; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.stripe_events TO praxiszeit_app;


--
-- Name: TABLE system_settings; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.system_settings TO praxiszeit_app;


--
-- Name: TABLE tenant_invoices; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tenant_invoices TO praxiszeit_app;


--
-- Name: TABLE tenants; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tenants TO praxiszeit_app;


--
-- Name: TABLE time_entries; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.time_entries TO praxiszeit_app;


--
-- Name: TABLE time_entry_audit_logs; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT ON TABLE public.time_entry_audit_logs TO praxiszeit_app;


--
-- Name: TABLE users; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.users TO praxiszeit_app;


--
-- Name: TABLE vacation_requests; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.vacation_requests TO praxiszeit_app;


--
-- Name: TABLE working_hours_changes; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.working_hours_changes TO praxiszeit_app;


--
-- Name: TABLE workstation_qualifications; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.workstation_qualifications TO praxiszeit_app;


--
-- Name: TABLE workstations; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.workstations TO praxiszeit_app;


--
-- Name: TABLE year_carryovers; Type: ACL; Schema: public; Owner: praxiszeit
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.year_carryovers TO praxiszeit_app;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: praxiszeit
--

ALTER DEFAULT PRIVILEGES FOR ROLE praxiszeit IN SCHEMA public GRANT SELECT,USAGE ON SEQUENCES TO praxiszeit_app;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: praxiszeit
--

ALTER DEFAULT PRIVILEGES FOR ROLE praxiszeit IN SCHEMA public GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO praxiszeit_app;


--
-- PostgreSQL database dump complete
--

\unrestrict SgZtr7I2mhqxWXjZwJKHxRDi9JP12VoFnIvsQbl1iNNzoGiLhmRtA1h6QZcb58k

