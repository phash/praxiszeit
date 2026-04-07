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

**Problem:** Der Catch-all `@app.get("/{full_path:path}")` fuer das Frontend-SPA
matcht `/api/dashboard` (ohne trailing slash) **vor** dem FastAPI-Router.
Ergebnis: API-Requests bekommen `index.html` statt JSON → `l.reduce is not a function`.

**Ursache:** FastAPI-Router verwenden standardmaessig trailing-slash Routen
(`/api/dashboard/`). Der Catch-all matcht die Variante ohne Slash zuerst.

**Loesung:** Im SPA-Fallback API-Pfade per 307-Redirect auf trailing slash weiterleiten:
```python
if full_path.startswith("api/"):
    return RedirectResponse(url=f"/{full_path}/", status_code=307)
```

**Datei:** `backend/app/main.py` → `spa_fallback()`

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

**Loesung:** In `cmd_start()` alle noeligen Config-Werte als Env-Vars setzen,
bevor Migrations/uvicorn gestartet werden. Pfad-Werte (z.B. `LICENSE_KEY_PATH`)
muessen absolut aufgeloest werden:
```python
if env_name in _PATH_KEYS and not Path(str_val).is_absolute():
    str_val = str(BASE_DIR / str_val)
```

**Datei:** `praxiszeit-server.py` → `cmd_start()`, Abschnitt "3b"

---

## Checkliste fuer zukuenftige Native Windows Deployments

- [ ] `praxiszeit.conf` korrekt ausgefuellt (admin, security, practice)
- [ ] `cookie_secure = false` wenn kein SSL (sonst Login-Cookie wird abgelehnt)
- [ ] SSL-Zertifikate unter `config/ssl/` ablegen falls HTTPS gewuenscht
- [ ] `license.key` unter `config/` ablegen
- [ ] Nach `net start PraxisZeit`: Logs pruefen auf "Application startup complete"
- [ ] Backup-Restore: `restore-backup.bat` nutzt `pause` → fuer Automation anpassen
- [ ] PostgreSQL-Port 5432 ist nur auf localhost gebunden (sicher)
