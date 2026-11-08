"""Aenderungsprotokoll als Beweismittel (#537, Audit 2026-11-07 A2-1/2/3/8).

``time_entry_audit_logs`` trug als Beleg nach § 16 Abs. 2 ArbZG nicht:

* A2-1: ``time_entry_id`` lag in der Pruefsumme, der Fremdschluessel ist
  ``ON DELETE SET NULL`` — jede Loeschung eines Zeiteintrags machte dessen
  Protokollzeilen fuer ``verify-integrity`` zu "manipuliert". Gleiches galt fuer
  ``change_request_id``. Ab hier gibt es unveraenderliche Kopien
  (``entry_ref``, ``changed_by_ref``, ``change_request_ref``), die beim Anlegen
  gesetzt und nie genullt werden; die Pruefsumme laeuft ueber sie. Der Backfill
  kopiert die heutigen Werte — Zeilen, deren Eintrag schon VOR dieser Migration
  geloescht wurde, bleiben uneindeutig (``legacy_entry_deleted``).
* A2-2: neue Zeilen tragen ``hash_version = 3``; die Pruefsumme deckt
  ``created_at`` und die Rohstempel ab. ``chain_seq``/``chain_prev``/
  ``chain_hash`` versiegeln die Zeilen je Mandant zu einer Kette (das Siegel
  setzt der taegliche Lauf bzw. die Pruefung), eine geloeschte Zeile hinterlaesst
  eine Luecke. Ein Trigger verweigert jedem Konto ausser der Eigentuemerin
  (Migrationsrolle) UPDATE und DELETE und laesst nur gehashte Neuzeilen zu; die
  App-Rolle verliert zusaetzlich die Rechte UPDATE/DELETE. Die drei erlaubten
  Aenderungen (Notiz-Scrub nach Art. 17, Versiegeln, Loeschen versiegelter
  Zeilen) laufen ueber SECURITY-DEFINER-Funktionen mit festem Zuschnitt. Das
  Kettenende (``system_settings.audit_chain_head``) bewegt nur
  ``pz_audit_set_head`` — auf das hoechste versiegelte Glied, nie zurueck; die
  Grenze fuer Altbestand ohne Pruefsumme (``audit_legacy_cutoff``) haelt diese
  Migration je Mandant fest. Beide Zeilen kann die App-Rolle nicht schreiben.
  Jede geloeschte Zeilen-id landet in ``audit_log_tombstones`` (nur
  Eigentuemerin) und darf nie wieder eingefuegt werden — erzwungen ueber den
  Primaerschluessel von ``audit_log_ids`` (jede je eingefuegte Zeilen-id, nur
  Eigentuemerin, nie geloescht); neue Zeilen der App-Rolle muessen einen
  gegenwaertigen ``created_at`` tragen.
* A2-3: die Rohstempel (``raw_start_time``/``raw_end_time``), das Ende der
  Anwesenheit und die nicht angerechneten Minuten stehen je Zeile vorher/nachher.
* A2-8: ``changed_by`` wird nullable mit ``ON DELETE SET NULL`` — die
  Endloeschung eines Verwalters haengt seine Zeilen nicht mehr auf den
  handelnden Verwalter um (das schrieb die Urheberschaft um), die Zeile zeigt
  "geloeschte Person"; ``changed_by_ref`` haelt die (zufaellige) Kennung fuer die
  Pruefsumme.

Downgrade: Funktionen, Trigger und Spalten fallen weg, die App-Rolle bekommt
UPDATE/DELETE zurueck. ``changed_by`` wird wieder NOT NULL — Zeilen, deren
Urheber endgeloescht wurde, bekommen dabei die betroffene Person als Urheber
(einziger gueltiger Verweis; nur fuer den Entwicklungs-Rueckweg gedacht).

Revision ID: 076_audit_chain
Revises: 075_contract_history
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "076_audit_chain"
down_revision = "075_contract_history"
branch_labels = None
depends_on = None

TABLE = "time_entry_audit_logs"
RAW_COLUMNS = (
    ("raw_start_time", sa.Time()),
    ("raw_end_time", sa.Time()),
    ("presence_end_time", sa.Time()),
    ("uncredited_minutes", sa.Integer()),
)

# Wer Eigentuemerin der Tabelle ist (oder Superuser), darf alles — Migrationen,
# Wiederherstellung (pg_restore laedt per COPY als Eigentuemerin) und die
# Fremdschluessel-Aktionen ON DELETE SET NULL (PostgreSQL fuehrt sie als
# Eigentuemerin der verweisenden Tabelle aus). Jedes andere Konto darf nur
# gehashte, unversiegelte Zeilen anfuegen.
GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    tbl_owner oid;
BEGIN
    SELECT relowner INTO tbl_owner FROM pg_class WHERE oid = TG_RELID;
    IF pg_has_role(current_user, tbl_owner, 'MEMBER')
       OR COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false) THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        -- auch Zeilen der Eigentuemerin bekommen ihre id fest vergeben
        -- (Trigger pz_audit_id_claim_owner, laesst eine vergebene id durch)
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
        -- (noch nicht festgeschrieben) sieht er nicht. Die id-Vergabe am
        -- Primaerschluessel von audit_log_ids (Trigger pz_audit_id_claim_writer
        -- nach diesem) laesst eine schon (auch parallel) vergebene id scheitern.
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
"""

# Die drei erlaubten Aenderungen. SECURITY DEFINER = sie laufen als
# Eigentuemerin (der Trigger laesst sie durch); FORCE RLS gilt auch fuer die
# Eigentuemerin, die Mandantenregel greift also mit den Einstellungen der
# aufrufenden Sitzung — zusaetzlich prueft jede Funktion den Mandanten selbst.
# Mandantenpruefung der Funktionen. Noetig, obwohl FORCE RLS gilt: im Betrieb
# ist die Eigentuemerin (Migrationsrolle) Superuser und umgeht RLS — innerhalb
# einer SECURITY-DEFINER-Funktion also auch die App. Massgeblich ist die
# Sitzung (session_user): ist SIE Superuser (Wartung, Tests als Eigentuemerin),
# gilt keine Mandantengrenze — wie bei jedem direkten Zugriff.
TENANT_OK_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_tenant_ok(p_tenant uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT current_setting('app.is_superadmin', true) = 'true'
        OR p_tenant = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = session_user), false)
$$;
"""

# Grabsteine (Review-Runde 3): jede ueber pz_audit_delete entfernte Zeilen-id.
# Nur die Eigentuemerin liest und schreibt die Tabelle (keine Rechte fuer die
# App-Rolle, RLS ohne FORCE — die Eigentuemerin darf nicht von Sitzungs-
# einstellungen abhaengen, die die App-Rolle selbst setzt). pz_audit_guard
# fragt sie ueber pz_audit_tombstoned (SECURITY DEFINER) ab.
TOMBSTONE_TABLE = """
CREATE TABLE audit_log_tombstones (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    deleted_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE audit_log_tombstones ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON audit_log_tombstones
USING (
    current_setting('app.is_superadmin', true) = 'true'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);
"""

# Jede je eingefuegte Zeilen-id (Review-Runde 5): der Primaerschluessel
# erzwingt "eine id kehrt nie zurueck" auch gegen ein paralleles
# pz_audit_delete (der Grabstein-Blick in pz_audit_guard sieht dessen noch
# offenen Grabstein nicht). Nie geloescht (ausser mit dem Mandanten), nur die
# Eigentuemerin hat Rechte, RLS ohne FORCE wie bei den Grabsteinen.
AUDIT_IDS_TABLE = """
CREATE TABLE audit_log_ids (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
);
ALTER TABLE audit_log_ids ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON audit_log_ids
USING (
    current_setting('app.is_superadmin', true) = 'true'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);
"""

# Vergibt die id jeder neuen Protokollzeile (Review-Runde 5) - als eigener
# SECURITY-DEFINER-Trigger (Review-Runde 7): die App-Rolle hat keine Rechte an
# audit_log_ids, und eine aufrufbare Hilfsfunktion liesse sich aus einem
# Trigger auf einer eigenen temporaeren Tabelle heraus missbrauchen (fremde
# ids vorab belegen, Existenz fremder ids abfragen). Eine Triggerfunktion ist
# nicht direkt aufrufbar; EXECUTE (nur fuer CREATE TRIGGER noetig) hat niemand
# ausser der Eigentuemerin, und sie verweigert jede andere Tabelle als
# time_entry_audit_logs. ON CONFLICT wartet auf eine parallele, noch offene
# Vergabe derselben id. Argument 'owner' (Schreiberin ist Eigentuemerin oder
# Superuser, vertraut - sie darf auch direkt loeschen): eine schon vergebene
# id geht durch; sonst wird sie abgelehnt.
CLAIM_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_claim() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    IF TG_RELID IS DISTINCT FROM 'public.time_entry_audit_logs'::regclass
       OR TG_OP <> 'INSERT' OR TG_LEVEL <> 'ROW' OR TG_WHEN <> 'BEFORE' THEN
        RAISE EXCEPTION 'pz_audit_claim: nur als Protokoll-Trigger'
            USING ERRCODE = '42501';
    END IF;
    INSERT INTO audit_log_ids (id, tenant_id) VALUES (NEW.id, NEW.tenant_id)
        ON CONFLICT (id) DO NOTHING;
    IF NOT FOUND AND TG_ARGV[0] IS DISTINCT FROM 'owner' THEN
        RAISE EXCEPTION 'time_entry_audit_logs: Zeilen-id % war schon vergeben, eine geloeschte Zeile darf nicht zurueckkehren', NEW.id
            USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END $$;
"""

# Wer schreibt? Wertet die WHEN-Bedingung der beiden Vergabe-Trigger aus -
# als aufrufendes Konto (current_user), anders als die SECURITY-DEFINER-
# Funktion pz_audit_claim, die nur noch die Eigentuemerin saehe.
WRITER_IS_OWNER_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_writer_is_owner() RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
    SELECT pg_has_role(current_user,
                       (SELECT relowner FROM pg_class
                         WHERE oid = 'public.time_entry_audit_logs'::regclass), 'MEMBER')
        OR COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false)
$$;
"""
# Schreibweise wie pg_get_triggerdef (Abgleich der Wiederherstellung)
CLAIM_TRIGGERS = (
    "CREATE TRIGGER pz_audit_id_claim_owner BEFORE INSERT ON time_entry_audit_logs "
    "FOR EACH ROW WHEN (pz_audit_writer_is_owner()) EXECUTE FUNCTION pz_audit_claim('owner')",
    "CREATE TRIGGER pz_audit_id_claim_writer BEFORE INSERT ON time_entry_audit_logs "
    "FOR EACH ROW WHEN ((NOT pz_audit_writer_is_owner())) "
    "EXECUTE FUNCTION pz_audit_claim('writer')",
)
CLAIM_REVOKE = "REVOKE ALL ON FUNCTION pz_audit_claim() FROM PUBLIC"

AUDIT_IDS_BACKFILL_SQL = """
INSERT INTO audit_log_ids (id, tenant_id)
SELECT id, tenant_id FROM time_entry_audit_logs
UNION
SELECT id, tenant_id FROM audit_log_tombstones
ON CONFLICT (id) DO NOTHING
"""

TOMBSTONED_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_tombstoned(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT EXISTS (SELECT 1 FROM audit_log_tombstones WHERE id = p_id)
$$;
"""

# Rechte an den Grabsteinen jedem Konto ausser der Eigentuemerin entziehen —
# auch die Default-Privilegien aus init-db-user.sql (ALTER DEFAULT PRIVILEGES)
# haben der App-Rolle beim Anlegen SELECT/INSERT/UPDATE/DELETE gegeben.
_OWNER_ONLY_REVOKE = """
DO $$
DECLARE
    r record;
BEGIN
    EXECUTE 'REVOKE ALL ON {t} FROM PUBLIC';
    FOR r IN
        SELECT DISTINCT a.grantee
          FROM pg_class c, aclexplode(c.relacl) a
         WHERE c.oid = 'public.{t}'::regclass
           AND a.grantee <> c.relowner
           AND a.grantee <> 0
    LOOP
        EXECUTE format('REVOKE ALL ON {t} FROM %s', r.grantee::regrole);
    END LOOP;
END $$;
"""
TOMBSTONE_REVOKE_BLOCK = _OWNER_ONLY_REVOKE.replace("{t}", "audit_log_tombstones")
AUDIT_IDS_REVOKE_BLOCK = _OWNER_ONLY_REVOKE.replace("{t}", "audit_log_ids")

# Gesiegeltes Kettenende (``system_settings.audit_chain_head``, Wert
# ``seq:hash:siegel``) — hier nur die Position, das Siegel prueft die App
# (Schluessel liegt ausserhalb der Datenbank). NULL = kein Kopf, -1 = zerstoert.
HEAD_SEQ_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_head_seq(p_tenant uuid) RETURNS bigint
LANGUAGE sql STABLE SET search_path = public, pg_temp AS $$
    SELECT CASE WHEN value ~ '^[0-9]{1,18}:[0-9a-f]*:[0-9a-f]+$'
                THEN split_part(value, ':', 1)::bigint ELSE -1 END
      FROM system_settings
     WHERE key = 'audit_chain_head' AND tenant_id = p_tenant
$$;
"""

# Versiegeln nur lueckenlos ab dem aktuellen Kettenende (Review-Runde
# 2026-11-07): sonst koennte die App-Rolle eine frische Zeile mit beliebiger
# Position versiegeln und gleich wieder loeschen.
SEAL_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_seal(p_ids uuid[], p_seqs bigint[], p_prevs text[], p_hashes text[])
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
"""

# Art.-17-Scrub: eine Notiz darf nur geleert, unveraendert gelassen oder
# anonymisiert werden — d. h. aus der alten entstehen, indem Teile durch die
# Kennzeichnung ``[anonymisiert]`` bzw. das Pseudonym ``deleted_<8 hex>``
# ersetzt werden (``admin_users._scrub_audit_log_notes``,
# ``lifecycle_service.anonymize_tenant``). Freier Text wird abgelehnt
# (Review-Runde 2, 2026-11-07). Pruefung ohne regulaeren Ausdruck aus
# Nutzertext: die festen Stuecke der neuen Notiz muessen in der alten in
# derselben Reihenfolge stehen, an jeder Kennzeichnung mindestens ein Zeichen
# dazwischen (frueheste Fundstelle je Stueck — fuer dieses Muster vollstaendig).
SCRUB_OK_FUNCTION = r"""
CREATE OR REPLACE FUNCTION pz_audit_scrub_ok(p_old text, p_new text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SET search_path = public, pg_temp AS $$
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
"""

# Pruefsumme: eine gehashte Zeile behaelt eine (die App rechnet sie ueber die
# neuen Notizen neu), eine ungehashte bleibt ungehasht — sonst liesse sich eine
# Zeile zu "Altbestand" herabstufen oder eine Altzeile mit frei gewaehltem
# Inhalt reinwaschen. hash_version aendert die Funktion nie.
NOTES_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_set_notes(p_id uuid, p_old_note text, p_new_note text, p_row_hash text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
"""

# Loeschen nur versiegelter Zeilen BIS zum gesiegelten Kettenende: ohne
# Kettenende (oder mit zerstoertem) wird nichts geloescht. Die App-Rolle kann
# das Kettenende weder loeschen noch umbenennen (pz_audit_head_guard); ein
# gefaelschtes Kettenende verraet das Siegel.
DELETE_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_delete(p_ids uuid[])
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
"""

# Kettenende und Altbestandsgrenze in system_settings: die App-Rolle darf
# beide weder anlegen, aendern, loeschen noch umbenennen (Review-Runde 2,
# 2026-11-07 — vorher durfte sie den Wert des Kettenendes frei schreiben, also
# einen aelteren Kopf zurueckspielen oder ihn hochsetzen, um pz_audit_delete
# mehr Glieder freizugeben). Das Kettenende bewegt nur pz_audit_set_head (laeuft
# als Eigentuemerin), die Grenze setzt allein diese Migration.
# Eigentuemerin/Superuser (Wartung, Wiederherstellung, Fremdschluessel-Kaskade
# beim Loeschen eines Mandanten) duerfen.
HEAD_GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_head_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
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
"""

# Kettenende setzen: nur auf das hoechste versiegelte Glied (Position UND
# Hash — so kann es niemand ueber die Kette hinaus hochsetzen) und nie zurueck.
# Einzige Ausnahme: "Kettenende neu setzen" der Verwaltung (p_reanchor) mit
# einer noch losen, gehashten Vermerk-Zeile ``audit_chain_reanchored`` aus
# derselben Transaktion — die wird gleich danach versiegelt und belegt das
# Zuruecksetzen dauerhaft. Ein alter Vermerk zaehlt nicht: geloeschte Zeilen
# kehren nie zurueck (Grabsteine), und der Anlagezeitpunkt muss frisch sein. Das
# Siegel (dritter Teil) prueft die App, der Schluessel liegt ausserhalb der DB.
SET_HEAD_FUNCTION = """
CREATE OR REPLACE FUNCTION pz_audit_set_head(p_tenant uuid, p_value text, p_reanchor boolean)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
END $$;
"""

# Feste Grenze fuer Altbestand ohne Pruefsumme (Review-Runde 2): je Mandant
# der Zeitpunkt der aeltesten gehashten Zeile bei Migration 076, ohne gehashte
# Zeile der Migrationszeitpunkt. Eine ungehashte Zeile, die juenger ist, hat
# jemand herabgestuft. Vorher rechnete die Pruefung MIN(created_at) jedes Mal
# neu — fielen die aeltesten gehashten Zeilen weg (Aufbewahrungsfrist,
# Endloeschung), rueckte die Grenze nach hinten. Format = canonical_timestamp.
LEGACY_CUTOFF_SQL = """
INSERT INTO system_settings (key, tenant_id, value, description)
SELECT 'audit_legacy_cutoff', t.id,
       to_char(COALESCE((SELECT min(a.created_at) FROM time_entry_audit_logs a
                          WHERE a.tenant_id = t.id AND a.row_hash IS NOT NULL), now())
               AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24\\:MI\\:SS.US'),
       'Aenderungsprotokoll: Grenze fuer Altbestand ohne Pruefsumme (#537)'
  FROM tenants t
ON CONFLICT (key, tenant_id) DO NOTHING
"""

# Funktionen: EXECUTE nicht fuer PUBLIC (PostgreSQL-Vorgabe), nur fuer die
# Konten, die das Protokoll schreiben (Recht INSERT — die App-Rolle).
_AUDIT_FUNCTIONS = (
    "pz_audit_seal(uuid[], bigint[], text[], text[])",
    "pz_audit_set_notes(uuid, text, text, text)",
    "pz_audit_set_head(uuid, text, boolean)",
    "pz_audit_scrub_ok(text, text)",
    "pz_audit_delete(uuid[])",
    "pz_audit_tenant_ok(uuid)",
    "pz_audit_head_seq(uuid)",
    "pz_audit_tombstoned(uuid)",
)
EXECUTE_BLOCK = """
DO $$
DECLARE
    r record;
    f text;
BEGIN
    FOREACH f IN ARRAY ARRAY[%s] LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %%s FROM PUBLIC', f);
        FOR r IN
            SELECT DISTINCT a.grantee
              FROM pg_class c, aclexplode(c.relacl) a
             WHERE c.oid = 'public.time_entry_audit_logs'::regclass
               AND a.privilege_type = 'INSERT'
               AND a.grantee <> c.relowner
               AND a.grantee <> 0
        LOOP
            EXECUTE format('GRANT EXECUTE ON FUNCTION %%s TO %%s', f, r.grantee::regrole);
        END LOOP;
    END LOOP;
END $$;
""" % ", ".join(f"'{f}'" for f in _AUDIT_FUNCTIONS)

# Rechte UPDATE/DELETE jedem Konto ausser der Eigentuemerin entziehen (auch
# PUBLIC). Die Rolle der App heisst je Installation anders (APP_DB_USER bzw.
# [database] app_user), deshalb aus der Rechteliste der Tabelle gelesen.
REVOKE_BLOCK = """
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT DISTINCT a.grantee
          FROM pg_class c, aclexplode(c.relacl) a
         WHERE c.oid = 'public.time_entry_audit_logs'::regclass
           AND a.privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE')
           AND a.grantee <> c.relowner
    LOOP
        IF r.grantee = 0 THEN
            EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON time_entry_audit_logs FROM PUBLIC';
        ELSE
            EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON time_entry_audit_logs FROM %s',
                           r.grantee::regrole);
        END IF;
    END LOOP;
END $$;
"""


def _changed_by_fk_name(conn):
    for fk in sa.inspect(conn).get_foreign_keys(TABLE):
        if fk.get("constrained_columns") == ["changed_by"]:
            return fk.get("name")
    return None


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("entry_ref", UUID(as_uuid=True), nullable=True))
    op.add_column(TABLE, sa.Column("changed_by_ref", UUID(as_uuid=True), nullable=True))
    op.add_column(TABLE, sa.Column("change_request_ref", UUID(as_uuid=True), nullable=True))
    op.add_column(TABLE, sa.Column("hash_version", sa.SmallInteger(), nullable=True))
    for side in ("old", "new"):
        for name, type_ in RAW_COLUMNS:
            op.add_column(TABLE, sa.Column(f"{side}_{name}", type_, nullable=True))
    op.add_column(TABLE, sa.Column("chain_seq", sa.BigInteger(), nullable=True))
    op.add_column(TABLE, sa.Column("chain_prev", sa.String(64), nullable=True))
    op.add_column(TABLE, sa.Column("chain_hash", sa.String(64), nullable=True))
    op.create_index(
        "uq_audit_tenant_chain_seq", TABLE, ["tenant_id", "chain_seq"], unique=True,
    )
    op.create_index("ix_time_entry_audit_logs_entry_ref", TABLE, ["entry_ref"])

    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"
    if is_pg:
        # FORCE RLS: sonst trifft der Backfill still 0 Zeilen (Muster 073/075)
        conn.execute(sa.text("SET LOCAL app.is_superadmin = 'true'"))
    result = conn.execute(sa.text(
        "UPDATE time_entry_audit_logs SET entry_ref = time_entry_id, "
        "changed_by_ref = changed_by, change_request_ref = change_request_id"
    ))
    count = result.rowcount

    # A2-8: Urheber darf endgeloescht werden, die Zeile bleibt.
    fk_name = _changed_by_fk_name(conn)
    with op.batch_alter_table(TABLE) as batch:
        if fk_name:
            batch.drop_constraint(fk_name, type_="foreignkey")
        batch.alter_column("changed_by", existing_type=UUID(as_uuid=True), nullable=True)
        batch.create_foreign_key(
            "time_entry_audit_logs_changed_by_fkey", "users", ["changed_by"], ["id"],
            ondelete="SET NULL",
        )

    if is_pg:
        conn.execute(sa.text(TOMBSTONE_TABLE))
        conn.execute(sa.text(TOMBSTONE_REVOKE_BLOCK))
        conn.execute(sa.text(TOMBSTONED_FUNCTION))
        conn.execute(sa.text(AUDIT_IDS_TABLE))
        conn.execute(sa.text(AUDIT_IDS_REVOKE_BLOCK))
        conn.execute(sa.text(AUDIT_IDS_BACKFILL_SQL))
        conn.execute(sa.text(GUARD_FUNCTION))
        conn.execute(sa.text(
            "CREATE TRIGGER pz_audit_guard_write BEFORE INSERT OR UPDATE OR DELETE "
            "ON time_entry_audit_logs FOR EACH ROW EXECUTE FUNCTION pz_audit_guard()"
        ))
        # nach pz_audit_guard_write (Trigger feuern in Namensreihenfolge)
        conn.execute(sa.text(CLAIM_FUNCTION))
        conn.execute(sa.text(CLAIM_REVOKE))
        conn.execute(sa.text(WRITER_IS_OWNER_FUNCTION))
        for trigger_sql in CLAIM_TRIGGERS:
            conn.execute(sa.text(trigger_sql))
        for fn in (TENANT_OK_FUNCTION, HEAD_SEQ_FUNCTION, SEAL_FUNCTION, SCRUB_OK_FUNCTION,
                   NOTES_FUNCTION, DELETE_FUNCTION, HEAD_GUARD_FUNCTION, SET_HEAD_FUNCTION):
            conn.execute(sa.text(fn))
        conn.execute(sa.text(LEGACY_CUTOFF_SQL))
        conn.execute(sa.text(
            "CREATE TRIGGER pz_audit_head_guard_write BEFORE INSERT OR UPDATE OR DELETE "
            "ON system_settings FOR EACH ROW EXECUTE FUNCTION pz_audit_head_guard()"
        ))
        conn.execute(sa.text(REVOKE_BLOCK))
        conn.execute(sa.text(EXECUTE_BLOCK))

    try:
        print(f"076: {count} Protokollzeilen mit festen Verweisen versehen")
    except UnicodeEncodeError:  # pragma: no cover - Windows-Konsole
        print(f"076: {count} Protokollzeilen")


def downgrade() -> None:
    conn = op.get_bind()
    is_pg = conn.dialect.name == "postgresql"
    if is_pg:
        conn.execute(sa.text("DROP TRIGGER IF EXISTS pz_audit_id_claim_owner ON time_entry_audit_logs"))
        conn.execute(sa.text("DROP TRIGGER IF EXISTS pz_audit_id_claim_writer ON time_entry_audit_logs"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_claim()"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_writer_is_owner()"))
        conn.execute(sa.text("DROP TRIGGER IF EXISTS pz_audit_guard_write ON time_entry_audit_logs"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_guard()"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_seal(uuid[], bigint[], text[], text[])"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_set_notes(uuid, text, text, text)"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_scrub_ok(text, text)"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_set_head(uuid, text, boolean)"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_delete(uuid[])"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_tenant_ok(uuid)"))
        conn.execute(sa.text("DROP TRIGGER IF EXISTS pz_audit_head_guard_write ON system_settings"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_head_guard()"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_head_seq(uuid)"))
        conn.execute(sa.text("DROP FUNCTION IF EXISTS pz_audit_tombstoned(uuid)"))
        conn.execute(sa.text("DROP TABLE IF EXISTS audit_log_ids"))
        conn.execute(sa.text("DROP TABLE IF EXISTS audit_log_tombstones"))
        # Kettenende gehoert zu den Spalten, die hier wegfallen
        conn.execute(sa.text("SET LOCAL app.is_superadmin = 'true'"))
        conn.execute(sa.text(
            "DELETE FROM system_settings WHERE key IN ('audit_chain_head', 'audit_integrity_last_check', "
            "'audit_legacy_cutoff')"
        ))
        conn.execute(sa.text(
            "DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'praxiszeit_app') THEN "
            "GRANT UPDATE, DELETE ON time_entry_audit_logs TO praxiszeit_app; END IF; END $$;"
        ))
        conn.execute(sa.text("SET LOCAL app.is_superadmin = 'true'"))
    conn.execute(sa.text(
        "UPDATE time_entry_audit_logs SET changed_by = user_id WHERE changed_by IS NULL"
    ))
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint("time_entry_audit_logs_changed_by_fkey", type_="foreignkey")
        batch.alter_column("changed_by", existing_type=UUID(as_uuid=True), nullable=False)
        batch.create_foreign_key(
            "time_entry_audit_logs_changed_by_fkey", "users", ["changed_by"], ["id"],
        )

    op.drop_index("ix_time_entry_audit_logs_entry_ref", table_name=TABLE)
    op.drop_index("uq_audit_tenant_chain_seq", table_name=TABLE)
    for name in ("chain_hash", "chain_prev", "chain_seq"):
        op.drop_column(TABLE, name)
    for side in ("new", "old"):
        for name, _ in reversed(RAW_COLUMNS):
            op.drop_column(TABLE, f"{side}_{name}")
    for name in ("hash_version", "change_request_ref", "changed_by_ref", "entry_ref"):
        op.drop_column(TABLE, name)
