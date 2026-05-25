# Native-Installer: PostgreSQL-Lifecycle-Fix (2026-05-25)

**Version:** 1.5.0 → 1.5.1
**Branch:** `fix/native-windows-pg-service`
**Symptom (Kunde):** Nach Windows-Installation per `praxiszeit-1.5.x-setup.exe` öffnet der
Wizard `https://localhost`, aber der Browser meldet `ERR_CONNECTION_REFUSED` — kein Port lauscht.

---

## Root Cause (Windows)

Mehrere ineinandergreifende Defekte:

1. **EDB-Leftover-Cluster.** `setup.bat` installiert PostgreSQL per EDB-Installer
   (`postgresql-installer.exe`), der den Dienst `PraxisZeit-PostgreSQL`
   (NetworkService) + ein **scram-initialisiertes** Datenverzeichnis mit Superuser
   `postgres` anlegt. Der nachgelagerte Cleanup (`sc delete` + `rd /s /q data\db`,
   `setup.bat` Z. 117–121) ist **racy** — solange der EDB-Dienst das Verzeichnis
   offen hält, schlagen Löschung/Wipe fehl. Ergebnis: scram-Cluster + Dienst bleiben.

2. **`pg_setup_database` nimmt `trust` an.** `praxiszeit-server.py` erwartet einen
   selbst per `initdb -A trust` gebauten Cluster (Superuser `praxiszeit`). Trifft es
   beim ersten `start` auf den EDB-scram-Cluster ohne `.db-credentials`, ruft es
   `psql … ALTER ROLE …` **ohne `PGPASSWORD` und ohne `-w`** auf → `psql` blockiert
   ewig an einer interaktiven Passwort-Abfrage (kein TTY im Dienst). uvicorn wird nie
   erreicht → `ERR_CONNECTION_REFUSED`. `.db-credentials` + `.secret-key` werden nie
   geschrieben (liegen hinter dem hängenden Aufruf).

3. **`postgres.exe` läuft nicht unter LocalSystem.** Der `PraxisZeit`-NSSM-Dienst läuft
   als **LocalSystem**. `postgres.exe` verweigert den Start unter einem Token mit
   Administrator-Mitgliedschaft. `pg_start()` startete PostgreSQL bisher als
   **Kindprozess** (`pg_ctl start`) — das schlägt unter LocalSystem fehl. Native
   Windows „funktionierte" nur zufällig, solange der EDB-Dienst (NetworkService)
   überlebte — und genau dann griff Defekt 2.

4. **SSL/Cookie-Mismatch.** Der Config-Writer schreibt **immer** `ssl_cert`/`ssl_key` +
   `cookie_secure = true`, aber `CertificateGenerator` wird **nie aufgerufen** →
   `config/ssl/` bleibt leer → uvicorn fällt auf Plain-HTTP zurück, der Browser lehnt
   das Secure-Cookie ab → Login kaputt (selbst nach Behebung von 1–3).

5. **Leere Logs.** Der NSSM-Dienst setzt kein `PYTHONUNBUFFERED` → stdout/stderr
   gepuffert → `service-*.log` bleiben 0 Byte, der Hang ist unsichtbar.

## Fix (`praxiszeit-server.py` + Installer)

- **PG als eigener Dienst auf Windows:** `pg_start()` registriert PostgreSQL via
  `pg_ctl register … -U "NT AUTHORITY\NetworkService"` und startet es als Dienst
  (statt Kindprozess). `pg_stop()` stoppt den Dienst. NetworkService bekommt per
  `icacls` FullControl auf das Datenverzeichnis. Unix bleibt bei `pg_ctl start`.
- **Cluster-Marker + Self-Healing:** `pg_init` schreibt `.praxiszeit-cluster` in
  PGDATA. Ein Datenverzeichnis ohne Marker **und** ohne `.db-credentials` wird als
  fremd erkannt, **zur Seite verschoben** (`db.foreign-<ts>`, nie gelöscht) und sauber
  neu initialisiert. Bestehende, credentialed Cluster bekommen den Marker per Migration
  nachgetragen.
- **`psql -w` überall:** kein interaktiver Passwort-Prompt mehr → Fail-fast statt Hang.
- **Self-Signed-Zert-Fallback:** `uvicorn_start` erzeugt ein Self-Signed-Zert, wenn SSL
  konfiguriert ist aber `cert.pem`/`key.pem` fehlen → HTTPS funktioniert, `cookie_secure`
  bleibt gültig.
- **`PYTHONUNBUFFERED=1` + `PYTHONUTF8=1`** im NSSM-Dienst (`install-service.bat`).

---

## Linux-Impact-Analyse

**Frische Linux-Installs sind vom Kunden-Bug NICHT betroffen:**

- `installer/linux/install.sh` nutzt **kein EDB** (PostgreSQL = gebündelte
  theseus-Binaries), legt **keinen** scram-Cluster an.
- Der systemd-Dienst läuft als **non-root User `praxiszeit`** (`User=praxiszeit`),
  daher startet `pg_ctl start` postgres problemlos als Kindprozess — der
  LocalSystem/Admin-Block (Defekt 3) existiert auf Linux nicht.
- `pg_init` baut den Cluster mit `initdb -A trust` → `pg_setup_database` läuft unter
  trust → **kein Hang**.

**Latentes, plattformübergreifendes Defizit (auch Linux):**

- Der eigentliche Defekt 2 (`psql` ohne `-w` + trust-Annahme) ist **nicht
  Windows-spezifisch**. Auf Linux ist er über einen Randfall erreichbar: ein bereits
  auf scram gehärteter Cluster, dessen `.db-credentials` verloren geht (manuelle
  Bereinigung, fehlerhaftes Restore, abgebrochener First-Init nach dem Härten) → beim
  nächsten `start` würde `psql` ohne `-w` im systemd-Kontext (kein TTY) **ewig hängen**.
  → Durch `psql -w` jetzt cross-platform behoben.

**Migrations-Hinweis (Linux & Windows):**

- Pre-1.5.1-Installs haben **keinen Cluster-Marker**. Der nachgetragene Marker-Backfill
  (nur wenn `.db-credentials` vorhanden) schützt gesunde Bestands-Installs vor einer
  versehentlichen Quarantäne-Reinit. Der Linux-Builder/Updater sollte den
  Upgrade-Pfad testen und sicherstellen, dass der Backfill greift (bzw. den Marker beim
  Update aktiv setzen).

→ Tracking: GitHub-Issue „Linux-Builder: psql-`-w`/Cluster-Marker-Migration verifizieren".
