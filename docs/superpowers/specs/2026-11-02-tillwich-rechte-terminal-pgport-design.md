# Erweiterte Rechte, Stempel-Terminal und PostgreSQL-Port (Windows)

**Stand:** 2026-11-02 · **Anlass:** Kundenanfrage Dr. Tillwich (Praxis Horb, Mails vom 01.11.2026), zweiter Kunde mit dem Wunsch nach einer Zwischenrolle (#190 wurde im Juni 2026 abgelehnt).
**Grundlage:** Code-Erfassung vom 2026-11-02 (Workflow `wf_039a4c87-d52`, nur lesend; Zeilenangaben beziehen sich auf master @ 1bffd77).

Kennzeichnung: **[Manuel]** = von Manuel entschieden, **[Kunde]** = Wunsch von Dr. Tillwich, **[Claude]** = Entscheidung von Claude, beim Lesen prüfen. Ohne Kennzeichnung = Folge aus Code oder CLAUDE.md-Regel.

---

## 1. Absicht

Kleine Praxen wollen einzelne Verwaltungsaufgaben an eine Mitarbeiterin abgeben (typisch: die MFA, die den Dienstplan macht), ohne ihr Vollzugriff zu geben. Außerdem wollen sie am Praxis-PC schnell stempeln, ohne dass sich jede Person mit Benutzername und Passwort anmeldet.

Beides ist **optional**. Der Praxisinhaber schaltet es auf der **Einstellungsseite in der App** ein **[Manuel]**. **Standard ist aus; dann verhält sich PraxisZeit exakt wie heute [Manuel].**

Der dritte Teil (PostgreSQL-Port) ist kein Kundenwunsch, sondern ein Fehler, der beim Prüfen der Kundenfrage auffiel: Unter Windows ist der Datenbank-Port 5432 fest eingebaut, und ein fremder PostgreSQL auf 5432 wird für den eigenen gehalten.

## 2. Ziele, Nicht-Ziele, Anti-Ziele

**Ziele**
- Teil A: Der Inhaber vergibt einzelnen Mitarbeitenden Einzelrechte aus einer festen Liste. Vorlage „Dienstplanung“ setzt mehrere auf einmal.
- Teil B: Freigegebene Geräte zeigen eine Stempel-Seite. Mitarbeitende stempeln dort per PIN ein und aus und beginnen/beenden die Pause.
- Teil B': Pause am laufenden Eintrag mit gestempelten Intervallen, auch im normalen StampWidget, für alle Kunden **[Manuel]**.
- Teil C: PostgreSQL-Port unter Windows einstellbar; fremder PostgreSQL wird erkannt statt verwechselt.

**Nicht-Ziele**
- Keine frei definierbaren Rollen, keine Rechte-Gruppen außer der einen Vorlage.
- Keine E-Mail-Benachrichtigung an Genehmigende (heute gibt es keine für Admins; `mail_service` sendet nur Signup-Mails). Genehmigende sehen offene Anträge wie heute über die Zähler im Menü.
- Kein Offline-Stempeln. Das Terminal braucht den Server im Praxisnetz.
- Kein Stempeln per Chipkarte/NFC.
- SaaS-Feinschliff (Mandantenauflösung in `/api/system/info`) bleibt zurückgestellt (Memory `feedback_saas-deferred`); F-026-Filter gelten trotzdem.

**Anti-Ziele (wäre ein Fehlschlag, auch wenn es technisch läuft)**
- Bei ausgeschalteten Schaltern ändert sich irgendetwas für bestehende Installationen (Antworten, Menüs, Exporte, Rechte).
- Jemand mit Einzelrechten kann sich selbst etwas genehmigen, sich selbst mehr Rechte geben, einen Admin anlegen oder das Konto des Inhabers übernehmen.
- Gesundheitsdaten (Art. 9 DSGVO) werden über einen neuen Weg sichtbar, ohne dass der Inhaber das eigene Recht dafür vergeben hat.
- Das Terminal zeigt einer Person Daten einer anderen (Saldo, Status bleibt stehen).
- Ein Terminal-Stempel umgeht eine Regel, die beim normalen Stempeln gilt (Ankersperre, Kappung, § 4/§ 5 ArbZG, Beschäftigungsfenster, Protokoll).

## 3. Reihenfolge und Umfang

Drei unabhängige Teile, je eigener Branch/PR, in dieser Reihenfolge **[Claude]**:

| Teil | Inhalt | Grobaufwand |
|---|---|---|
| C | PostgreSQL-Port Windows | 2–4 Tage |
| B | Stempel-Terminal + Pausen-Intervalle am laufenden Eintrag | 2–2,5 Wochen |
| A | Erweiterte Rechte (inkl. Vorarbeit A0) | 2–3 Wochen |

C zuerst, weil klein und ein echter Fehler. B vor A, weil B den Recht „PIN neu vergeben“ aus A nicht braucht (bis A kommt, vergibt nur der Admin PINs) und weil die Pause-Funktion allen Kunden nützt. Jeder Teil ist für sich auslieferbar.

Migrationen ab **074** (Head ist 073), Revision-ID ≤ 32 Zeichen.

---

## 4. Teil C — PostgreSQL-Port unter Windows

### 4.1 Befund
- 5432 fest in `praxiszeit-server.py`: `pg_is_running` (:269), `_database_url` (:299), `pg_init` schreibt `port = 5432` (:403); `pg_start` vertraut `pg_is_running` (:646).
- Weitere `psql`/`pg_dump`-Aufrufe ohne `-h/-p` (:1104, :1883, :1995, :2280, :2669) fallen unter Windows auf libpq-Standard `localhost:5432`; `pg_env` setzt/entfernt `PGHOST`/`PGPORT` nur unter Unix (:194–205).
- `pg_is_running` erkennt nicht, wessen Cluster antwortet. Läuft ein fremder PostgreSQL auf 5432, meldet `pg_start` „already running“, der eigene Dienst startet nie, App/Backup/Restore sprechen mit dem fremden Server (Windows-Gegenstück zu #174).
- `setup.bat` ruft den EDB-Installer mit `--serverport 5432` (:123); der EDB-Dienst wird danach entfernt (:142–145). `restore-backup.template.bat` hat `-p 5432` (:64). Der GUI-Installer kennt keinen DB-Port; `PraxisZeitConfigWriter` schreibt in `[database]` keinen Port.
- `pg_init` kehrt bei vorhandenem PGDATA früh zurück (:339–341) → bestehende Installationen bekommen eine geänderte `postgresql.conf` nie.
- Linux/macOS: Cluster ist socket-only (`listen_addresses=''`), kein TCP-Port → **nicht betroffen, außer Umfang**.

### 4.2 Lösung
1. **Einstellung** `[database] port` in `config/praxiszeit.conf`, Standard 5432, gelesen über `get_config_value`. Kein Eintrag = 5432 = heutiges Verhalten. Nicht auf der Einstellungsseite: ohne laufende Datenbank ist die App nicht erreichbar **[Claude]**.
2. **Eine Quelle** im Server-Skript, z. B. `pg_port(config) -> int`; alle 5432-Stellen nutzen sie. Unter Windows setzt `pg_env` `PGHOST=localhost` und `PGPORT=<port>` hart (entfernt geerbte Werte), damit auch die Aufrufe ohne `-h/-p` den eigenen Cluster treffen.
3. **Eigenen Cluster erkennen:** `pg_is_running` gilt nur als „läuft“, wenn `PG_DATA/postmaster.pid` existiert, die PID lebt und die Port-Zeile (Zeile 4) zum konfigurierten Port passt; danach `pg_isready` auf diesem Port. Antwortet der Port, aber `postmaster.pid` fehlt oder passt nicht → **fremder Server**: klare Meldung „Port <p> ist von einem anderen PostgreSQL belegt. In config\praxiszeit.conf unter [database] einen freien Port eintragen (z. B. 5433) und den Dienst neu starten.“ und Abbruch über den bestehenden `should_give_up`-Pfad, kein Absturz-Kreislauf. Die genaue Methode (postmaster.pid vs. `pg_ctl status -D`) wählt der Builder; Bedingung: portunabhängig an PG_DATA gebunden.
4. **Bestehende Installationen:** Beim Start vergleicht das Skript den konfigurierten Port mit der `port =`-Zeile im von PraxisZeit verwalteten Block der `postgresql.conf`. Weicht er ab, wird nur diese Zeile ersetzt (idempotent), bevor der Cluster startet. Bei Standard 5432 und unveränderter Datei: keine Änderung.
5. **GUI-Installer:** Seite „Ports“ bekommt das Feld „Datenbank-Port (nur Windows)“, Standard 5432, mit derselben Belegt-Prüfung wie HTTPS (Warnung, kein Hartstopp); `PraxisZeitConfigWriter` schreibt `[database] port`. `setup.bat` übergibt den Wert an `--serverport`.
6. **`restore-backup.bat`:** liest den Port zur Laufzeit (Weg wählt der Builder, z. B. `praxiszeit-server.py print-db-port` oder Auslesen der conf); CRLF-Regel und `test_native_restore.py` beachten.
7. **Update-Pfad** (`update-wizard.ps1`) braucht nichts Eigenes, weil Punkt 4 beim Start greift; Builder prüft das im Emulator.

### 4.3 Tests und Nachweis
- Unit: URL mit konfiguriertem Port (Pin-Test `test_native_pg_lifecycle.py:392` anpassen), Standard ohne Eintrag = heutiger String; Fremd-PG unter Windows simuliert (Port antwortet, keine passende `postmaster.pid` → Meldung, kein „already running“); conf-Rewrite idempotent.
- Windows-Emulator (`tools/win-test`): (a) Update einer 1.21-Installation ohne Eintrag → unverändert lauffähig; (b) frische Installation, auf 5432 läuft vorher ein fremder PostgreSQL → Installer warnt, mit 5433 läuft PraxisZeit, Login + Stempeln + Backup + Restore gehen. `tools/win-test`-pgpass-Zeilen auf den Port umstellen.
- Doku: `docs/NATIVE-BETRIEB.md` (Regel „drei Stellen zusammen pflegen“ um Port erweitern), `docs/INSTALL-NATIVE.md`, `docs/NATIVE-WINDOWS-PITFALLS.md`, `docs/setup-windows.md`, `docs/ARC42.md:573` (Risiko „nur dedizierte Hosts“ entschärfen), pzweb `AnleitungWindows.tsx` Abschnitt „Netzwerk und Port“.

---

## 5. Teil B — Stempel-Terminal und Pause am laufenden Eintrag

### 5.1 Schalter
- Mandanten-Einstellung `stamp_terminal_enabled`, Standard **aus** [Manuel]. Checkliste der bestehenden Schalter (Muster `shift_planning_enabled`): `admin_settings._ALLOWED_SETTINGS` + `_BOOL_SETTINGS`, Router-Gate mit 404 (`require_…_enabled`), `main.system_info` + Leak-Guard `test_deployment_mode.py`, `systemStore.isStampTerminalEnabled()` (`=== true`), Karte in `Settings.tsx`, E2E `OWNED_SETTINGS` oder `e2e/tests/tenant-settings/` + Negativ-Spec „aus → 404“.
- Aus = Terminal-Seite und `/api/terminal/*` antworten 404; PIN-Felder im Profil und in der Benutzerverwaltung sind ausgeblendet. **Die Pause-Funktion (5.6) hängt NICHT an diesem Schalter**, siehe dort.
- Schalterwechsel schreibt eine Zeile in `security_events` (neu, heute protokolliert `PUT /admin/settings` nichts) **[Claude]**.

### 5.2 Geräte
- Neue Tabelle `terminal_devices` (`id`, `tenant_id` NOT NULL, `name`, `token_hash`, `created_by` FK users, `created_at`, `last_seen_at`, `revoked_at`, Zähler für Fehlversuche), RLS ENABLE+FORCE + `tenant_isolation` (Muster Migration 071), F-026-Filter, Grant für `praxiszeit_app`, `purge_user` (created_by auf handelnden Admin umhängen).
- **Einrichten:** Der Admin meldet sich am Gerät an, klickt in den Einstellungen „Dieses Gerät als Stempel-Terminal einrichten“ und gibt einen Namen ein. Der Server erzeugt ein zufälliges Geräte-Token, speichert nur den Hash und setzt es als **HttpOnly-Cookie** (Pfad `/api/terminal`, lange Laufzeit, SameSite=Strict, `Secure` gemäß `cookie_secure`) **[Claude]**. Danach meldet sich der Admin ab und das Gerät öffnet `/terminal`.
- **Verwalten:** Liste der Geräte in den Einstellungen (Name, eingerichtet von/am, zuletzt gesehen), „Sperren“ setzt `revoked_at`; gesperrt → Terminal zeigt „Gerät nicht freigegeben“.
- Das Geräte-Token ist **kein** Benutzer-Login: eigener Typ, `get_current_user` akzeptiert nur `type=='access'` (`middleware/auth.py:37`) und lehnt es damit ab. Mandant kommt aus dem Gerätedatensatz (`set_tenant_context(db, device.tenant_id)`), nie aus `/api/system/info`.
- Geräte zählen nicht gegen Lizenz-/Sitzplatzgrenzen.
- Einrichten/Sperren → `security_events` (`terminal_device_enabled`/`terminal_device_revoked`).

### 5.3 PIN
- Neue Spalten an `users`: `pin_hash`, `pin_set_at` (Migration 074 bzw. Folge-Nummer). Hash wie Passwort (`auth_service.hash_password`).
- **Identifikation: erst Namen antippen, dann PIN [Manuel].** PIN 4–6 Ziffern, selbst gewählt oder vom Admin vergeben, muss **nicht** mandantenweit eindeutig sein. Triviale PINs (`0000`, `1234`, Geburtsjahr-artige 19xx/20xx) werden abgelehnt [Claude].
- Eigene PIN: im Profil „Stempel-PIN festlegen/ändern“, nur nach Passwort-Eingabe (wie 2FA-Einrichtung, F1), damit ein Access-Token allein keine PIN setzen kann [Claude].
- PIN vergeben: der Admin in der Benutzerverwaltung („Neue Stempel-PIN“), später auch Personen mit dem Recht „PIN neu vergeben“ (Teil A). Die PIN wird einmal angezeigt, danach nie wieder lesbar [Kunde: Einsehen geht nicht, Neu-Vergeben schon]. Jede Vergabe → `security_events` (`terminal_pin_reset`, actor `user:<id>`).
- Personalnummer als PIN gibt es nicht [Manuel].
- Fehlversuche werden **in der Datenbank** gezählt (nicht wie der Login-Lockout im Prozessspeicher, der Neustarts nicht überlebt und je Worker getrennt ist): **je Person** (Spalten `pin_failed_count`, `pin_locked_until` an `users`; z. B. 5 Fehlversuche → Sperre steigend ab 1 Minute; nach 10 in Folge Terminal-Stempeln für diese Person gesperrt, bis Admin oder `reset_pin` eine neue PIN vergibt) **und je Gerät** (Gesamtzahl Fehlversuche je Zeitfenster, gegen Durchprobieren über viele Namen). Sperren → `security_events` (`terminal_lockout`). Der IP-basierte slowapi-Limiter ist dafür ungeeignet (alle Eingaben kommen von derselben IP); er bleibt als grober Schutz zusätzlich davor. Genaue Schwellen wählt der Builder.
- Anonymisierung (`anonymize_user`, `lifecycle_service.anonymize_tenant`) leert `pin_hash`; Art.-20-Export (`/me/export`, `_user_dict`) nennt nur „Stempel-PIN gesetzt am …“, nie den Hash.

### 5.4 Ablauf am Terminal
- Route `/terminal` außerhalb von `ProtectedRoute` und `Layout`, ohne `authStore`, Vollbild, große Tasten.
- Startbildschirm: Kacheln mit den Namen der aktiven Mitarbeitenden des Mandanten, die eine PIN haben (`GET /api/terminal/people`, nur Anzeigename + ID, sortiert; mit Suche/Buchstabenleiste ab ca. 20 Personen) [Manuel: Namen antippen]. Status (wer ist da) wird auf den Kacheln **nicht** angezeigt [Claude, Datenschutz].
- Name antippen → Zahlenfeld → `POST /api/terminal/identify` (Geräte-Cookie + Personen-ID + PIN) → Antwort: Vorname/Name, Status (ausgestempelt / eingestempelt seit HH:MM / in Pause seit HH:MM) und ein **kurzlebiges Vorgangs-Token** (z. B. 60 s, nur für diese Person, nur Stempelaktionen) **[Claude]**.
- Knöpfe je nach Status: „Einstempeln“, „Pause beginnen“, „Pause beenden“, „Ausstempeln“.
- Anzeige **nur** Name, Status, Uhrzeit der Aktion und Warnungen. Kein Saldo, kein Journal, keine Abwesenheiten [Claude, aus Datenschutz].
- Nach jeder Aktion und nach ca. 10 s ohne Eingabe zurück zu den Namenskacheln; das Vorgangs-Token verfällt.
- Warnungen (§ 5 Ruhezeit, Kappung, MiLoG …) werden wie im StampWidget angezeigt (`showArbzgWarnings`-Texte), aber nur für die gerade identifizierte Person.
- **§ 4 beim Ausstempeln:** Reicht die Pause des Tages nicht, lehnt der Server wie heute mit 400 ab, der Eintrag bleibt offen. Das Terminal bietet dann „Pause nachtragen (Minuten)“ an und, wenn `break_exception_allowed` an ist, ein Textfeld für den Grund [Claude]. Entschieden wird über `break_validation_service.break_waiver_rejection` wie an allen Schreibpfaden.
- Lizenz abgelaufen → Schreibsperre greift wie beim normalen Stempeln (`LicenseReadOnlyMiddleware`), Terminal zeigt den Hinweis.
- CSRF: Terminal-POSTs tragen kein Sitzungs-Cookie. Der Builder sichert sie über SameSite=Strict am Geräte-Cookie plus Pflicht-Header; die Terminal-Pfade kommen bewusst in die Ausnahmeliste von `middleware/csrf.py` oder bekommen ein eigenes Double-Submit-Cookie. Entscheidung dokumentieren.
- nginx: neue Pfade liegen unter `location ^~ /api/`; `/terminal` ist eine SPA-Route (Fallback-Middleware greift).
- Offline: nicht unterstützt; ohne Server zeigt das Terminal „Keine Verbindung zum Server“.

### 5.5 Gleiche Regeln wie normales Stempeln
- **Refactoring zuerst:** Die Rümpfe von `clock_in` (`time_entries.py:510–671`) und `clock_out` (`:673–901`) wandern in `services/clock_service.py` (z. B. `clock_in(db, user, *, actor_id, source, note)` / `clock_out(db, user, *, actor_id, source, break_minutes, waiver)`). Die bestehenden Routen werden dünne Hüllen. **Verhalten bitgleich** (gleiche Antworten, Warnungen, Statuscodes, Protokollzeilen); bestehende Tests müssen ohne Änderung grün bleiben.
- Damit durchläuft das Terminal dieselbe Kette: `lock_user_row` zuerst (P5), `_get_open_entry` mit Sperre, `_close_stale_entry`, Beschäftigungsfenster, `clamp`/`clamp_with_segments` mit `grace_for_entry`, Duplikatprüfung mit gekapptem Beginn, § 3/§ 4/§ 5/§ 6, MiLoG-Warnungen, `_create_audit_log`.
- **Protokoll:** Terminal-Aktionen schreiben `TimeEntryAuditLog` mit `changed_by = Person selbst` und neuen `source`-Werten < 40 Zeichen (z. B. `terminal_clock_in`, `terminal_clock_out`, `terminal_pause`); Labels in `frontend/src/constants/auditSources.ts`. Heute schreibt `clock_in` keine Protokollzeile; das Terminal-Einstempeln schreibt eine (um das Gerät festzuhalten), das normale Einstempeln bleibt unverändert [Claude].
- **Gerät im Protokoll:** neue, **nicht gehashte** Spalte `time_entry_audit_logs.terminal_device_id` (nullable FK, `ON DELETE SET NULL`). `_HASHED_FIELDS` in `core/audit_integrity.py` bleibt unverändert (CLAUDE.md: keine neue gehashte Spalte, `verify-integrity`) [Claude].

### 5.6 Pause am laufenden Eintrag (Teil B')
- Gilt **für alle Kunden**, unabhängig von beiden Schaltern [Manuel]: neue Knöpfe „Pause beginnen“/„Pause beenden“ auch im StampWidget. **Bewusste Ausnahme vom Anti-Ziel „Standard wie bisher“**: Der Knopf ist neu sichtbar; wer ihn nicht nutzt, stempelt und rechnet exakt wie heute (Pause beim Ausstempeln eintippen bleibt).
- **Pausen als Intervalle [Manuel]:** neue Spalte `time_entries.pause_intervals` (JSON-Liste `[{"start": "HH:MM", "end": "HH:MM"|null}]`, `none_as_null=True`, nur als ganzer Wert neu zuweisen wie `work_blocks`); ein Eintrag ohne `end` = laufende Pause (höchstens einer). NULL = keine gestempelten Pausen = heutiges Verhalten.
- `POST …/pause-start`: nur bei offenem Eintrag von heute ohne laufende Pause; hängt `{start: jetzt}` an (auf Minute). Ankersperre zuerst. Protokollzeile.
- `POST …/pause-end`: setzt `end = jetzt` am laufenden Intervall und berechnet `break_minutes` neu (s. u.). Protokollzeile.
- **Keine Doppelabzüge:** Der Teil eines Pausen-Intervalls, der in eine nicht angerechnete Strecke fällt (Lücke zwischen Blöcken, vor/nach der Hülle; Quelle `work_window_service.clamp_with_segments`), zählt **nicht** in `break_minutes`. Ziel: `net_hours`-Formel (Python-Hybrid und SQL, Paritätstest) bleibt unverändert, weil `break_minutes` schon die bereinigte Summe trägt. Geht das nicht sauber, Formel + SQL-Zwilling + `test_net_hours_parity_pg.py` mitändern; Entscheidung dokumentieren.
- **§ 4 mit Intervallen [Manuel]:** Hat ein Eintrag `pause_intervals`, zählen für § 4 nur Abschnitte von mindestens 15 Minuten (volle Länge, auch der Teil in einer Lücke, denn dort wird ja nicht gearbeitet); kürzere Pausen senken die Netto-Zeit, erfüllen § 4 aber nicht. Ohne Intervalle gilt die heutige Summenregel. Umsetzung in `break_validation_service.validate_daily_break` (Tagesaggregat über alle Einträge), Frontend-Zwilling `utils/breakValidation.ts::computeBreakError` wortgleich.
- **Manuelles Ändern der Pause** (Bearbeiten, Änderungsantrag, Ausstempeln mit abweichendem Wert, XLS-Import): Der eingegebene Wert gewinnt, `pause_intervals` wird auf NULL gesetzt (alte Intervalle stehen in der Protokollzeile), § 4 zählt dann wieder als Summe [Claude]. Unverändert zurückgeschickte Werte sind keine Änderung (`time_relevant_change`).
- **`break_minutes` beim Ausstempeln bleibt ein Ersetzen** (API unverändert, `time_entries.py:781`) [Claude]. StampWidget und Terminal belegen das Pausenfeld mit der gestempelten Summe vor; wird der Wert unverändert geschickt, bleiben die Intervalle; weicht er ab, gilt die Regel „Manuelles Ändern“. „Pause nachtragen“ am Terminal addiert im Frontend auf den Wert.
- **Ausstempeln während laufender Pause:** Intervall wird zuerst zum Ausstempelzeitpunkt beendet und eingerechnet, dann normal ausgestempelt (§ 4 sieht die Intervalle).
- **Auto-Close** (`_close_stale_entry`) mit laufender Pause: Intervall endet am wirksamen Ende des Eintrags [Claude].
- **Live-Anzeigen:** `/clock-status` (`today_net_minutes`, `_running_credited_minutes`) und der Frontend-Zwilling `utils/workBlocks.ts::runningCreditedMinutes` ziehen gestempelte und laufende Pausen ab und melden `pause_intervals`; wortgleiche Testfälle in beiden Zwillingen.
- **Anzeigen/Exporte:** Journal und Zeiteintrags-Detail zeigen die Intervalle („Pause 12:00–12:30“); §16-Exporte bekommen **keine** neue Spalte in diesem Schritt [Claude] (neue Spalten nur hinter der letzten, eigener Folgeauftrag).
- Die Lücke zwischen Blöcken (`uncredited_minutes`) und `break_minutes` bleiben getrennte Größen wie heute.

### 5.7 Tests
- Backend: Pausen-Intervalle (Überschneidung mit Lücke/Hülle zählt nicht doppelt, § 4 nur Abschnitte ≥ 15 min, manuelles Ändern setzt NULL, Paritätstest grün); Schalter aus → 404 an allen Terminal-Routen; Gerät gesperrt/fremder Mandant → abgewiesen; PIN falsch → Zähler/Sperre/`security_events`; Terminal-Ein-/Ausstempeln läuft durch dieselben Prüfungen (je ein Test für Ankersperre, Kappung, § 4-Ablehnung bleibt offen, § 5-Warnung, Beschäftigungsfenster); Protokoll mit Gerät; Pause (beginnen/beenden/ausstempeln während Pause/Auto-Close/§ 4 mit gesammelter Pause); Refactoring: komplette bestehende Suite unverändert grün.
- Postgres: Ankersperre-Reihenfolge (`test_write_path_locks.py`-Muster), RLS für `terminal_devices` (`test_tenant_rls.py`), Cross-Tenant (`test_cross_tenant_api.py`).
- Frontend: Terminal-Seite (Rücksprung nach Zeitablauf, nur Name/Status), StampWidget-Pause, `runningCreditedMinutes`-Zwilling.
- E2E: Gerät einrichten → PIN vergeben → am Terminal ein/Pause/aus → Eintrag im Journal; Schalter aus → 404.

---

## 6. Teil A — Erweiterte Rechte

### 6.1 Vorarbeit A0 (eigener kleiner PR, behebt bestehende Lücke)
- `export_service._absence_export_label` (`:608–610`, auch von `ods_export_service` genutzt) maskiert nur `sick` + `reason_id`; OTHER und PAID_LEAVE bleiben lesbar. Auf `MASKED_ABSENCE_TYPES` umstellen (#514-Regel). Ohne diesen Fix wäre „Berichte drucken ohne Gesundheitsdaten“ undicht.
- F-020-Protokollzeilen in `reports.py` (`:76–77`, `:224`, `:345`, `:461` …) tragen den Leser statt der betroffenen Person als `user_id`; korrigieren.

### 6.2 Schalter und Speicherung
- Mandanten-Einstellung `extended_permissions_enabled`, Standard **aus** [Manuel]; dieselbe Schalter-Checkliste wie 5.1. Ob der Schalter in `/api/system/info` (öffentlich, vor Login) gehört oder nur in die angemeldeten Antworten: **nur angemeldet** [Claude] — das Frontend liest ihn aus `/me`/Login-Antwort; Leak-Guard bleibt unverändert.
- Speicherung: neue Spalte `users.permissions` (JSON-Liste von Schlüsseln, `JSON().with_variant(JSONB(), "postgresql")`) [Claude]. Rolle bleibt `ADMIN`/`EMPLOYEE`, **keine neue Enum-Rolle**: alle heutigen `== UserRole.ADMIN`-Prüfungen bleiben damit standardmäßig sicher.
- **Wirksame Rechte** an genau einer Stelle (z. B. `permission_service.effective_permissions(db, user)`): ADMIN → alle; EMPLOYEE → gespeicherte Liste **nur wenn** der Schalter an ist, sonst leer. Schalter aus → Rechte bleiben gespeichert, wirken nicht [Claude, von Manuel bestätigt].
- Wirksame Rechte werden je Anfrage aus der DB berechnet (`get_current_user` lädt den User ohnehin neu) → Entzug wirkt sofort serverseitig. Kein `token_version`-Bump bei Rechteänderung (sonst fliegt die Person raus) [Claude]; das Frontend lädt `/me` beim Start, beim Seitenwechsel ins Admin-Menü und nach jedem 403 neu.
- Neue Felder in `UserResponse` **und** `UserListResponse` (Login, Impersonation, `GET /admin/users`), sonst setzt `UserForm` sie beim Bearbeiten zurück (bekannter MiLoG-Fehler).

### 6.3 Rechte-Liste

| Schlüssel | Bedeutung | Heutige Flächen (Auszug) |
|---|---|---|
| `approve_vacation` | Urlaubsanträge sehen, genehmigen, ablehnen [Kunde] | `admin_vacations.py` (:34, :51, :73; PATCH :331, Storno :377) |
| `approve_change_requests` | Korrekturanträge sehen, genehmigen, ablehnen, Sammel-Genehmigung [Kunde]; inkl. Abwesenheitsanträge (Genehmigungsregeln unverändert). „Genehmigen und anerkennen“ und Anträge mit `request_credit_override` bleiben beim Admin; die Sammel-Genehmigung überspringt sie und nennt die Zahl [Claude] | `admin_change_requests.py` (:139, :153, :185, :207, :1353) |
| `shift_planning` | Dienstplanung (Arbeitsplätze, Pläne, Slots, Zuordnung, Generator, Einweisungen) [Kunde] | `shift_planning.py` alle `require_admin` + `is_admin`-Zweige (:528, :681, :734, `_build_plan_detail`) |
| `edit_time_entries` | Zeiteinträge anderer anlegen, ändern, löschen; protokolliert [Kunde] | `admin_time_entries.py` (:71, :237, :653), Admin-Journal-Ansicht |
| `create_employees` | Mitarbeitende anlegen mit dem vollen Formular inkl. Startpasswort, Arbeitszeit/Blöcken, Urlaub, Stundenzählung, §18, MiLoG — nur ohne Rolle und Rechte [Manuel]. Spätere Vertrags-/Arbeitszeit-Änderungen und Passwort-Neusetzen bleiben beim Admin | `POST /admin/users` (:1141) |
| `archive_employees` | Mitarbeitende deaktivieren/reaktivieren, ausblenden [Kunde] | `DELETE /admin/users/{id}` (:1445), reactivate (:1474), toggle-hidden (:1558) |
| `view_balances` | Salden/Übersichten anderer sehen, Berichte erstellen und drucken [Kunde] | `users-overview` (:529), `team-schedule`, `reports.py` alle, Admin-Journal lesend, `dashboard` Team-Zweige (:371, :430) |
| `reset_pin` | Stempel-PIN anderer neu vergeben [Kunde]; nur sichtbar, wenn Terminal-Schalter an | neu aus Teil B |
| `view_health_data` | Zusatzrecht: Krankheitstage, Abwesenheitsgründe, „Kind krank“-Zähler unmaskiert [Kunde, Ausgestaltung Claude] | siehe 6.5 |

- Vorlage „Dienstplanung“ = `shift_planning` + `approve_vacation` + `approve_change_requests` + `view_balances` [Claude]; nur ein Vorbelegen der Häkchen, keine eigene Rolle.
- `view_health_data` wirkt nur zusammen mit einem Recht, das solche Daten zeigt (`view_balances`, `approve_vacation`, `approve_change_requests`, `edit_time_entries`); allein vergeben ist es wirkungslos und die UI verhindert das.
- Lesezugriff auf die Benutzerliste (Namen, aktiv, Abteilung) bekommt jede Person mit mindestens einem Recht, das sie braucht (Dienstplanung lädt `/admin/users`) [Claude]; Vertrags-/Stundenfelder nur mit `view_balances`, Bearbeiten nur über die jeweiligen Rechte.

### 6.4 Feste Grenzen (gelten immer, auch mit allen Rechten)
- **Nie am eigenen Datensatz:** Wer delegierte Rechte nutzt, kann eigene Urlaubs-/Korrekturanträge nicht genehmigen, ablehnen, ändern oder stornieren, eigene Zeiteinträge nicht über die Verwaltungswege ändern, sich nicht selbst archivieren, keine eigene PIN über `reset_pin` vergeben (die eigene PIN läuft über den normalen Profilweg) [Kunde]. Serverseitig unbedingt, nicht wie heute nur „wenn es einen anderen Admin gibt“ (`admin_vacations.py:133`, `admin_change_requests.py:316`).
- **Vier-Augen-Ausnahme bleibt Inhaber-Sache:** Die heutige Regel „einziger Admin darf sich selbst genehmigen“ bleibt für ADMIN unverändert; delegierte Personen zählen **nicht** als „anderer Admin“ (`_tenant_has_other_active_admin`) [Claude] — sonst ändert sich das Verhalten für den Inhaber, sobald jemand Rechte bekommt.
- **Wen die Rechte betreffen:** Genehmigen, Korrigieren und Salden sehen wirken auf alle Personen des Mandanten außer der handelnden selbst, also auch auf andere Personen mit Rechten und auf den Inhaber [Claude; Kunde nannte nur „nicht selbst“].
- **Ziele von Personalaktionen:** `archive_employees` und `reset_pin` wirken nur auf Mitarbeitende **ohne** Admin-Rolle und **ohne** eigene Rechte [Claude]. Neu angelegte Personen sind immer `EMPLOYEE` ohne Rechte; `role` im Body wird für Nicht-Admins verworfen bzw. mit 400 abgelehnt.
- **Nur der Admin:** Rechte vergeben/entziehen, Rollen ändern, Passwort neu setzen (`set-password` :1414; das Startpasswort beim Anlegen darf `create_employees`), 2FA, Impersonation, endgültig löschen (`purge` :947), anonymisieren (:797), Einstellungen, Abwesenheitsgründe, Betriebsferien, Feiertage, Jahresabschluss, Überträge, Arbeitszeit-Änderungen/Blöcke (wirken rückwirkend auf Soll und Saldo), Anerkennen (`credit-override` :617), XLS-Import, Abwesenheiten für andere buchen/löschen (`absences.py:386`, `:932`), Protokoll (`audit-log`, enthält unmaskierte Notizen), Sicherheitsereignisse, Backups, Updates, Fehlerprotokoll, Abrechnung [Claude: alles nicht in der Kundenliste].
- **Eigene Daten mit Admin-Abkürzungen:** Heutige `role === 'admin'`-Abkürzungen am eigenen Datensatz (TimeTracking direkt bearbeiten statt Antrag, AbsenceCalendar-Löschsperren, direkte Urlaubsbuchung `absences.py:419`) bleiben strikt ADMIN und werden **nicht** auf Rechte umgestellt.
- **Letzter-Admin-Schutz** (`lock_active_admins_and_user`) zählt weiter nur ADMIN.

### 6.5 Gesundheitsdaten (Art. 9)
Ohne `view_health_data` sieht eine delegierte Person „abwesend“ statt Typ/Grund, so wie Kolleginnen heute im Teamkalender [Claude, von Manuel bestätigt]. Durchzusetzen **serverseitig**, nie über einen Query-Parameter vom Client:
- `absences._hide_health_data` (:69–79): unmaskiert für ADMIN, die Person selbst **oder** `view_health_data`.
- Admin-Journal (`journal.py:20–76`): `include_health_data` wird ohne Recht auf False gezwungen (Standard von `get_journal` ist True!).
- `reports.py`: alle `include_health_data`-Parameter ohne Recht auf False zwingen; mit A0 maskiert der Export richtig.
- Antrags-Warteschlangen (`admin_change_requests.py:153`, `admin_vacations.py:51`): Abwesenheits-CRs ohne Recht mit maskiertem Typ, Grund und Notiz.
- `users-overview`: `child_sick_used`/`child_sick_cap` (:626–632) nur mit Recht.
- Protokollzeilen „Gesundheitsdaten gelesen“ nur, wenn tatsächlich unmaskiert ausgeliefert wurde, mit der betroffenen Person als Subjekt.

### 6.6 Durchsetzung im Backend
- Neue Abhängigkeit `require_permission("<key>")` neben `require_admin`. Routen-Gruppen aus 6.3 wechseln von `require_admin` auf `require_permission`; alle anderen bleiben `require_admin`.
- Router mit Router-weitem `require_admin` (`admin_users`, `admin_time_entries`, `reports`, `team_schedule` …) werden auf Endpunkt-Ebene aufgeteilt; kein Endpunkt darf beim Umbau seine Admin-Sperre verlieren. Der Builder erstellt dafür eine **Inventarliste aller ~150 `require_admin`-Nutzungen und ~45 Inline-Rollenprüfungen** mit Zielzustand je Zeile (Recht X / bleibt Admin / bleibt Admin, weil eigener Datensatz) und legt sie dem PR bei.
- Inline-`role == ADMIN`-Zweige in Mitarbeiter-Routen (`time_entries`, `absences`, `dashboard`, `change_requests`, `shift_planning`): nur die in 6.3 genannten Zweige wechseln auf ein Recht **und** „Ziel ≠ ich selbst“; der Rest bleibt ADMIN.
- Schutztest: ein Test, der jede Route der App aufzählt (FastAPI-Routenliste) und gegen die Inventarliste prüft — neue Admin-Routen ohne Eintrag lassen ihn scheitern (Muster `test_no_live_work_blocks_read.py`) [Claude].

### 6.7 Frontend
- `User`-Typ + `authStore` bekommen `permissions` (wirksame Rechte) und einen zentralen Helfer `can(perm)` (ADMIN ⇒ immer true).
- Routen: `ProtectedRoute` bekommt `permission="…"`; das `/admin`-Elternelement lässt Personen mit mindestens einem Recht durch, jede Kindroute prüft ihr Recht.
- Menü: `adminNavItems` je Eintrag mit Recht; Abschnitt „Verwaltung“ erscheint, wenn mindestens ein Eintrag übrig bleibt; **nur die erlaubten Seiten sind sichtbar, gesperrte tauchen nicht auf** [Claude, Menüfrage nicht beantwortet]. Antragszähler laufen nur mit dem jeweiligen Recht.
- Admin-Startseite (`AdminDashboard`, mischt Team-Zahlen mit System-Karten wie `UpdateBanner`): für delegierte Personen nur die Team-Karten passend zu ihren Rechten [Claude].
- Gemischte Seiten mit Knopf-Sperren: `Users.tsx` (Anlegen/Archivieren sichtbar je Recht; Passwort, Impersonation, Löschen, Anonymisieren, Rollen- und Rechte-Auswahl nur ADMIN), `UserForm` (Rollenauswahl nur ADMIN; neuer Bereich „Rechte“ nur ADMIN, nur bei Schalter an), `MonthlyJournal` (`isAdminView` aus `can('edit_time_entries')`, `include_health_data` aus `can('view_health_data')` statt fest `true`), `Reports`, `VacationApprovals`, `ChangeRequests`.
- Eigene-Daten-Abkürzungen in `TimeTracking`/`AbsenceCalendarPage` bleiben `role === 'admin'`.
- Hilfe: delegierte Personen sehen das Mitarbeiter-Handbuch; das Admin-Handbuch bekommt ein Kapitel „Erweiterte Rechte“, das Mitarbeiter-Handbuch einen Abschnitt „Wenn Sie Verwaltungsrechte haben“ [Claude].

### 6.8 Protokoll und DSGVO
- `security_events`: `permissions_changed` (alt → neu), `user_created`, `extended_permissions_toggled`; Labels in `SecurityEventsCard.EVENT_LABELS`; alle < 50 Zeichen.
- Delegierte Korrekturen schreiben wie heute `TimeEntryAuditLog` mit `changed_by = handelnde Person`.
- Art.-20-Export (`/me/export`, `lifecycle_service._user_dict`): eigene Rechte mit ausgeben; Anonymisierung leert `permissions`.
- `purge_user`: neue Spalten liegen an `users`, keine neue FK-Tabelle in Teil A.

### 6.9 Tests
- Je Recht: mit Recht 200, ohne 403, Schalter aus trotz gespeichertem Recht 403.
- Je Grenze aus 6.4 ein Test (eigener Antrag, eigener Eintrag, Admin als Ziel, Person mit Rechten als Ziel, Rolle im Body, Rechte-Selbstvergabe).
- Art. 9: ohne `view_health_data` maskiert in Journal, Berichten (XLSX/ODS/PDF), Warteschlangen, Übersicht; mit Recht unmaskiert.
- Routen-Inventar-Schutztest (6.6).
- Bestehende Suite unverändert grün (Anti-Ziel „Standard wie bisher“).
- E2E: neuer Fixture-Benutzer „Dienstplanung“ in `global-setup`; Menü zeigt nur erlaubte Seiten; Genehmigen fremder Anträge geht, eigener nicht; Schalter aus → Verwaltung verschwindet. `create_handbuch_testdata.py` bekommt eine Person mit Rechten für Screenshots.

---

## 7. Gemeinsames

- **Doku-Sync (5 Flächen, `scripts/check-doc-sync.sh all`):** Handbücher Admin/Mitarbeiter + Cheatsheets, `DocViewer.tsx` + `helpContent.tsx`, Spiegel `frontend/public/help`, pzweb-Anleitungen, `SchnellstartAdmin`; `docs/GLOSSAR.md` (Begriffe „Stempel-Terminal“, „Stempel-PIN“, „Erweiterte Rechte“); `docs/uc` neue Use-Cases; `docs/SECURITY.md` (Bedrohungsmodell PIN/Gerät); CLAUDE.md-Regelzeilen je Teil.
- **Release-Gate** wie 1.20.0 (Migration an `users`/`time_entries`): nach dem Update auf .131 nativ **und** Docker-Bundle echter Login, Ein-/Ausstempeln, `GET /api/admin/users`; bei Teil C zusätzlich Windows-Emulator.
- **Migrationen gegen Prod-DB-Kopie testen** (Memory `project_prod-db`), Round-Trip auf Wegwerf-PG 18.

## 8. Rückfragen und Entscheidungen

Alle geklärt am 2026-11-02 [Manuel]:
1. Terminal-Identifikation: Namen antippen, dann PIN (5.3/5.4).
2. Gestempelte Pausen als Intervalle, § 4 nur Abschnitte ≥ 15 min, kein Doppelabzug (5.6).
3. `create_employees` mit vollem Formular (6.3).
4. Pause-Knopf für alle Kunden (5.6).
