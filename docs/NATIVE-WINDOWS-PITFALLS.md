# Native Windows Installation – Bekannte Fallstricke

Dieses Dokument beschreibt Probleme die beim ersten Native-Deployment auf Windows Server 2019
mit PostgreSQL 18.3, Python 3.13 und NSSM aufgetreten sind, und deren Loesungen.

## 1. psql `-v` Variable-Interpolation funktioniert nicht mit `-c`

**Problem:** `psql -v pw=xxx -c "ALTER ROLE ... PASSWORD :'pw'"` wirft `syntax error at or near ":"`.
Die psql-Variable `:'pw'` wird bei `-c` nicht substituiert.

**Betroffen:** PostgreSQL 18.3 Windows, moeglicherweise auch andere Versionen.

**Loesung:** Direkte SQL-Strings mit escaped Password verwenden:
```python
escaped_pw = _escape_pg_password(password)
subprocess.run([psql, "-U", user, "-d", "postgres",
    "-c", f"ALTER ROLE {user} PASSWORD '{escaped_pw}'"], ...)
```

**Datei:** `praxiszeit-server.py` → `pg_setup_database()`

---

## 2. Python 3.13 Glob-Expansion in subprocess-Argumenten

**Problem:** `subprocess.Popen(["uvicorn", ..., "--forwarded-allow-ips", "*"])` — der `*`
wird als Glob expanded. Alle Dateien im CWD (`alembic.ini`, `app/`, etc.) werden als
uvicorn-Argumente uebergeben → `Got unexpected extra arguments`.

**Betroffen:** Python 3.13+ auf Windows.

**Loesung:** Niemals `"*"` als Argument verwenden. Stattdessen explizite Werte:
```python
"--forwarded-allow-ips", "127.0.0.1,::1"
```

**Datei:** `praxiszeit-server.py` → `uvicorn_start()`

---

## 3. NSSM-Service: SYSTEM-Account kann Dateien nicht lesen

**Problem:** Der Windows-Service laeuft als `NT AUTHORITY\SYSTEM`. Dateien die mit
`icacls /inheritance:r /grant:r USERNAME:(R,W)` geschuetzt werden, sind fuer SYSTEM
nicht lesbar → `PermissionError: [Errno 13] Permission denied: '.db-credentials'`

**Ursache:** `os.environ["USERNAME"]` im SYSTEM-Kontext gibt den Maschinenaccount
zurueck (z.B. `T2MEDSERVER$`), nicht `SYSTEM`.

**Loesung:** Bei `_save_credentials()` immer auch `SYSTEM:(R,W)` hinzufuegen:
```python
cmds.append(["icacls", str(creds_file), "/grant", "SYSTEM:(R,W)"])
```

**Datei:** `praxiszeit-server.py` → `_save_credentials()`

---

## 4. cp1252 UnicodeEncodeError bei Emoji-Output

**Problem:** `print("🚀 Starting PraxisZeit...")` crasht mit
`UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f680'`

**Ursache:** NSSM leitet stdout/stderr in Logdateien um. Windows Default-Encoding
ist cp1252, das keine Emojis unterstuetzt.

**Loesung:** `PYTHONUTF8=1` als Environment-Variable fuer alle Python-Subprozesse:
```python
env["PYTHONUTF8"] = "1"
```

**Datei:** `praxiszeit-server.py` → `uvicorn_start()`

---

## 5. SPA-Fallback faengt API-Routen ab

> **Hinweis:** Dieses Problem wurde zuerst mit einem 307-Redirect geloest,
> dann aber durch die Middleware-Loesung in Pitfall #9 vollstaendig ersetzt.
> Die aktuelle Loesung ist `SPAFallbackMiddleware` (siehe #9).

**Problem:** Der Catch-all `@app.get("/{full_path:path}")` fuer das Frontend-SPA
matcht `/api/dashboard` (ohne trailing slash) **vor** dem FastAPI-Router.
Ergebnis: API-Requests bekommen `index.html` statt JSON → `l.reduce is not a function`.

**Ursache:** FastAPI-Router verwenden standardmaessig trailing-slash Routen
(`/api/dashboard/`). Der Catch-all matcht die Variante ohne Slash zuerst.

**Loesung:** ~~307-Redirect~~ → ersetzt durch Middleware (siehe Pitfall #9).

**Datei:** `backend/app/main.py` → `SPAFallbackMiddleware`

---

## 6. FRONTEND_DIR relativer Pfad im Native-Modus

**Problem:** `FRONTEND_DIR = "../frontend/dist"` (Default in config.py) funktioniert nicht,
weil CWD = `app/backend/` ist und Frontend in `app/frontend/` liegt (ohne `dist/`).
Ergebnis: `{"detail": "Frontend not found"}`.

**Loesung:** In `uvicorn_start()` den absoluten Pfad setzen:
```python
env["FRONTEND_DIR"] = str(APP_DIR / "frontend")
```

**Datei:** `praxiszeit-server.py` → `uvicorn_start()`

---

## 7. Config-to-Environment-Variable Bridge

**Problem:** `config.py` hat einen TOML-Loader der `praxiszeit.conf` liest, aber
der sucht relativ zum CWD (`config/praxiszeit.conf`). Da Alembic und uvicorn aus
`app/backend/` gestartet werden, wird die Config unter `../../config/praxiszeit.conf`
nicht gefunden → `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` fehlen.

**Loesung:** In `cmd_start()` alle noetigen Config-Werte als Env-Vars setzen,
bevor Migrations/uvicorn gestartet werden. Pfad-Werte (z.B. `LICENSE_KEY_PATH`)
muessen absolut aufgeloest werden:
```python
if env_name in _PATH_KEYS and not Path(str_val).is_absolute():
    str_val = str(BASE_DIR / str_val)
```

**Datei:** `praxiszeit-server.py` → `cmd_start()`, Abschnitt "3b"

---

## 8. SECRET_KEY nicht persistiert — Session-Verlust bei Restart

**Problem:** `SECRET_KEY` wird bei jedem Service-Restart neu generiert.
Alle JWTs (Access + Refresh) werden sofort ungueltig → alle User fliegen raus.

**Ursache:** `secrets.token_hex(32)` wurde in-memory generiert, aber nie auf Disk
geschrieben. Bei NSSM-Restart (neuer Prozess) geht der Key verloren.

**Loesung:** Key in `config/.secret-key` persistieren, bei Folgestarts laden:
```python
sk_file = CONFIG_DIR / ".secret-key"
if sk_file.is_file():
    sk = sk_file.read_text().strip()
else:
    sk = secrets.token_hex(32)
    sk_file.write_text(sk)
```

**Datei:** `praxiszeit-server.py` → `cmd_start()`, Abschnitt "SECRET_KEY"

---

## 9. SPA Catch-All Route verursacht 405 Method Not Allowed

**Problem:** `@app.get("/{full_path:path}")` als SPA-Fallback registriert eine
GET-Route fuer jeden Pfad. POST/PUT/DELETE auf API-Endpoints (z.B. Zeiteintrag
erstellen/bearbeiten) bekommen 405 statt an den API-Router weitergeleitet zu werden.

**Ursache:** FastAPI sieht den Pfad-Match mit dem Catch-All, aber die HTTP-Methode
(POST/PUT/DELETE) passt nicht zu GET → 405 Method Not Allowed.

**Loesung:** SPA-Fallback als Middleware statt als Route:
```python
class SPAFallbackMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if (request.method == "GET"
                and response.status_code == 404
                and not request.url.path.startswith("/api/")):
            return Response(content=_index_html, media_type="text/html")
        return response
```

**Datei:** `backend/app/main.py` → `SPAFallbackMiddleware`

---

## 10. cookie_secure=true ohne SSL

**Problem:** `Set-Cookie: refresh_token; Secure` wird vom Browser bei HTTP-
Verbindungen abgelehnt → Login schlaegt fehl (Token wird nicht gespeichert).

**Loesung:** In `praxiszeit.conf`: `cookie_secure = false` wenn kein SSL.
Sobald SSL eingerichtet ist, wieder auf `true` setzen.

**Datei:** `config/praxiszeit.conf` → `[security]`

---

## 11. VC++ Runtime fehlt auf frischem Windows → initdb.exe Exit 0xC0000135

**Problem:** Auf einem frisch aufgesetzten Windows schlaegt der allererste Start
fehl, der Dienst loopt endlos mit wachsendem Backoff. Im Log
(`logs\service-stderr.log`):
```
subprocess.CalledProcessError: Command '[... initdb.exe ...]' returned non-zero exit status 3221225781.
```
`3221225781` = `0xC0000135` = `STATUS_DLL_NOT_FOUND`: der OS-Loader kann
`initdb.exe` gar nicht erst starten, weil eine importierte DLL fehlt (kein
initdb-Output, nur der Python-Wrapper-Traceback).

**Ursache:** Die EDB-PostgreSQL-18-Binaries sind MSVC-gebaut und brauchen die
Microsoft Visual C++ Runtime (`vcruntime140*.dll` / `vcruntime140_1.dll` /
`msvcp140.dll`). `setup.bat` rief den EDB-Installer frueher mit
`--install_runtimes 0` auf → der Redist wurde NICHT installiert. Auf Dev- und
Bestandsmaschinen faellt das nie auf, weil dort fast immer schon ein
VC++-Redist von anderer Software liegt; ein blankes Windows hat ihn nicht.

**Loesung:**
1. `setup.bat`: `--install_runtimes 1` (= Default des EDB-Installers; idempotent,
   systemweit). Der Installer installiert den passenden vcredist intern.
2. `praxiszeit-server.py`: `_check_pg_launchable()` uebersetzt die NTSTATUS-Codes
   `0xC0000135`/`0xC0000142` in eine klare, umsetzbare Fehlermeldung
   (`PgRuntimeMissingError`) statt einer opaken CalledProcessError-Endlosschleife.
   Eingehaengt in `pg_init` (initdb) und den Windows-`pg_start`-Timeout-Pfad.

**Sofort-Workaround (Bestandsinstallation, ohne neues Paket):**
`https://aka.ms/vs/17/release/vc_redist.x64.exe` als Administrator installieren,
dann `net start PraxisZeit`.

**Dateien:** `installer/windows/setup.bat`,
`praxiszeit-server.py` → `pg_init()` / `_check_pg_launchable()`.
Regressionstest: `backend/tests/test_native_pg_lifecycle.py::TestVcRuntimeDiagnostic`.
**Feldreport:** 2026-05-26 (Kunden-Erstinstallation), behoben in 1.5.3.

**Update-Pfad-Härtung (ab 1.5.4):** `setup.bat --install_runtimes 1` deckt nur die
**Erstinstallation** ab — ein In-Place-Update (`update-wizard.ps1`, auch der
`setup.exe`-Update-Modus via `-Headless`) startet den EDB-Installer **nicht**.
Daher bündelt `build-release.sh` jetzt `bin/vc_redist.x64.exe`, und
`update-wizard.ps1` führt es in `Step-VcRedist` idempotent aus
(`/install /quiet /norestart`, Exit `0/1638/3010/1641` = OK), best-effort/
nicht-fatal vor dem Service-Start. Für Bestands-Installs unkritisch (liefen schon
= Runtime da), schützt aber Maschinen ohne Runtime.

**setup.bat-Detail:** KEINE Klammern in den `REM`-Kommentaren im `()`-Block —
unbalancierte Klammern beenden den Block vorzeitig (Batch-Parser).

---

## 12. Windows-Python-Deps müssen beim BUILD ins Bundle (nicht install-zeitig)

**Problem (vor 1.5.1):** Die Python-Abhängigkeiten wurden install-zeitig per
`setup.bat`-`pip` nachgeladen — unzuverlässig (Netz/Timing). Auf Maschinen mit
einem **System-Python 3.13** sah pip dessen User-Site, meldete „bereits erfüllt"
und installierte **NICHTS** ins Bundle → der Dienst (LocalSystem) fand
`alembic`/`uvicorn` nicht → `ERR_CONNECTION_REFUSED` im Browser.

**Lösung (1.5.1):** `build-release.sh` Phase 5 installiert die
cp313-win_amd64-Wheels **beim Build** vor nach
`bin/python/Lib/site-packages` (analog Linux) → die Kunden-Installation braucht
**keinen** PyPI-Download. Beim pip-Aufruf `PYTHONNOUSERSITE=1` setzen (ignoriert
ein System-Python-User-Site) + Import-Verify (Build **und** `setup.bat`).

---

## Checkliste fuer zukuenftige Native Windows Deployments

- [ ] `praxiszeit.conf` korrekt ausgefuellt (admin, security, practice)
- [ ] `cookie_secure = false` wenn kein SSL (sonst Login-Cookie wird abgelehnt)
- [ ] SSL-Zertifikate unter `config/ssl/` ablegen falls HTTPS gewuenscht
- [ ] `license.key` unter `config/` ablegen
- [ ] Nach `net start PraxisZeit`: Logs pruefen auf "Application startup complete"
- [ ] Kein "Generated SECRET_KEY" bei Folgestarts (muss "Generated and saved" nur beim ersten Mal)
- [ ] Backup-Restore: `restore-backup.bat` nutzt `pause` → fuer Automation anpassen
- [ ] PostgreSQL-Port 5432 ist nur auf localhost gebunden (sicher)
- [ ] API-Endpoints testen: `POST /api/time-entries` darf nicht 405 geben
- [ ] VC++ Runtime vorhanden (`setup.bat --install_runtimes 1` erledigt das automatisch; sonst `initdb.exe` Exit `0xC0000135`, siehe #11)
