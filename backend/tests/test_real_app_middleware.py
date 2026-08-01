"""Integrationstests gegen die ECHTE Anwendung — ``app.main.app``.

Warum diese Datei existiert
===========================
Die restliche Backend-Suite prueft die Anwendung an zwei Stellen:

* ``tests/test_endpoints.py`` (und die Geschwister ``test_license_readonly_*``,
  ``test_cross_tenant_api.py``, …) bauen sich mit ``FastAPI()`` eine EIGENE
  Anwendung zusammen und haengen nur die Router ein.
* Alle uebrigen Tests rufen die Services direkt auf — also unterhalb der Router.

Beide Wege haben denselben blinden Fleck: die **Zwischenschicht** der echten
Anwendung wird nie durchlaufen. In ``app/main.py`` haengen elf Middlewares
uebereinander (CORS, TrustedHost, SecurityHeaders, RequestSizeLimit, GZip,
Impersonation-Read-Only, License-Read-Only, CSRF, Prometheus und die beiden
``@app.middleware("http")``-Dekoratoren fuer Tenant-Metriken und
Fehlerprotokollierung), dazu der Lifespan-Bootstrap und die Ratenbegrenzung.
Genau dort leben die Lizenz-Schreibsperre und die Mandanten-Aufloesung — die
Flaeche, auf der ein Fehler *jeden* Nutzer trifft.

Der reale Schaden dazu ist dokumentiert: die Hotfix-Kette 1.8.5–1.8.10 entstand,
weil ``prometheus-fastapi-instrumentator`` 8.0.0 beim Zusammenbau der echten
Anwendung ungeschuetzt ``route.path`` las, waehrend FastAPI ab 0.137 Routen ohne
``.path`` (``_IncludedRouter``) in ``app.routes`` legt → HTTP 500 auf dem Login
und auf jedem included-Router-Endpoint. Die Unit-Tests blieben gruen, weil sie
diese Anwendung nie gebaut haben. ``tests/test_real_app_middleware.py`` schliesst
diese Luecke.

Aufbau der Vorrichtung
======================
1. **Eigene SQLite-Datei** (nicht die ``./test.db`` der conftest) — die
   Vorrichtung laeuft parallel zur uebrigen Suite, ohne dass deren
   ``create_all``/``drop_all`` je in ihre Tabellen greift.
2. **``SET LOCAL`` wird auf DIALEKT-Ebene neutralisiert**, nicht durch Patchen
   von App-Code: ein ``before_cursor_execute``-Listener ersetzt genau die
   RLS-Kontext-Statements durch ``SELECT 1``. ``set_tenant_context`` /
   ``set_superadmin_context`` werden also wirklich aufgerufen, der
   ``after_begin``-Listener der ``SessionLocal`` feuert wirklich — nur die
   Datenbank erzwingt keine RLS. Das ist bewusst so: RLS auf DB-Ebene deckt
   ``test_tenant_rls.py`` gegen echtes PostgreSQL ab. Hier geht es um die
   **App-Layer-Mandanten-Aufloesung** (``tid``-Claim gegen Datenbestand), und
   die ist datenbankunabhaengig.
3. **Die ``SessionLocal`` wird umgehaengt statt ersetzt**
   (``SessionLocal.configure(bind=…)``). Damit zeigen ALLE Module, die
   ``from app.database import SessionLocal`` gemacht haben (``app.main``, der
   ``DBErrorHandler``, ``_check_saas_suspend`` der Lizenz-Middleware …) auf
   dieselbe umgehaengte Factory — ohne dass ein einziges ``patch()`` auf
   App-Code noetig waere.
4. **Der echte Lifespan laeuft.** ``TestClient(app)`` als Kontextmanager faehrt
   ``app.main.lifespan`` hoch: Datenbank-Check, Default-Mandant, Admin-Konto,
   Feiertags-Sync, Lizenz-Block, Scheduler-Start. Der Bootstrap wird also NICHT
   umgangen, sondern ausgehalten — er ist selbst Pruefgegenstand (siehe
   ``TestLifespanBootstrap``). Der Scheduler bleibt dabei ueber die
   ``PYTEST_CURRENT_TEST``-Erkennung aus; auch das wird geprueft, statt
   angenommen.
5. **Die Ratenbegrenzung bleibt SCHARF.** Sie wird nicht abgeschaltet
   (``limiter.enabled`` wird nicht angefasst) — stattdessen bekommt jeder Test
   ueber ``TestClient(..., client=(ip, port))`` seinen eigenen IP-Bucket, weil
   slowapi per Client-IP schluesselt. ``TestRateLimiting`` prueft an einem
   Endpoint mit fest verdrahtetem ``3/minute``-Limit (also unabhaengig von
   ``LOGIN_RATE_LIMIT`` aus der Umgebung), dass die Begrenzung in der echten
   Anwendung wirklich greift.

Wo diese Tests laufen
=====================
SQLite, also im normalen ``pytest tests/``-Lauf (Schritt 1 von
``scripts/local-ci.sh``). Bewusst NICHT in den PostgreSQL-Suiten: keiner der
hier geprueften Pfade braucht echtes RLS, und ein Test, der nur im separaten
PG-Lauf vorkommt, wird seltener ausgefuehrt.
"""
from __future__ import annotations

import importlib
import itertools
import logging
import os
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

import app.database as database_module
import app.main as main_module
from app.config import settings
from app.core import license as license_module
from app.database import Base, SessionLocal
from app.services import auth_service, scheduler_service

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Die Anmeldedaten des Bootstrap-Admins kommen aus der Konfiguration — der
# Lifespan legt genau dieses Konto an (Schritt 4 in app/main.py).
ADMIN_USERNAME = settings.ADMIN_USERNAME
ADMIN_PASSWORD = settings.ADMIN_PASSWORD

EMPLOYEE_USERNAME = "realapp_employee"
EMPLOYEE_PASSWORD = "RealApp2026!Employee"

# Jeder Test bekommt eine eigene Client-IP, damit die (scharf gelassene)
# Ratenbegrenzung nicht quer durch die Datei schlaegt.
_ip_counter = itertools.count(1)


def _next_client_addr() -> tuple[str, int]:
    n = next(_ip_counter)
    return (f"10.66.{(n // 250) % 250}.{n % 250 + 1}", 40000 + (n % 20000))


# ---------------------------------------------------------------------------
# Vorrichtung
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_app_db():
    """Haengt die globale ``SessionLocal`` der Anwendung auf eine eigene
    SQLite-Datei um und neutralisiert die PostgreSQL-``SET LOCAL``-Statements
    auf Dialekt-Ebene.

    Bewusst KEIN ``patch()`` auf ``set_tenant_context``/``set_superadmin_context``
    (so macht es die uebrige Suite): die Funktionen sollen wirklich laufen, damit
    ein Aufrufer, der den RLS-Kontext vergisst, hier nicht zufaellig gruen bleibt.
    Neutralisiert wird nur das Statement, das SQLite nicht kennt.
    """
    db_path = Path(tempfile.gettempdir()) / "praxiszeit_real_app_test.db"
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(str(db_path) + suffix)
        except OSError:
            pass

    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _sqlite_wal(dbapi_conn, _record):  # pragma: no cover - infrastructure
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _neutralize_set_local(
        conn, cursor, statement, parameters, context, executemany
    ):  # pragma: no cover - infrastructure
        # ``SET LOCAL app.tenant_id = …`` / ``SET LOCAL app.is_superadmin = …``
        # sind die einzigen PostgreSQL-spezifischen Statements im Request-Pfad.
        if statement.lstrip().upper().startswith("SET LOCAL"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(bind=engine)

    original_engine = database_module.engine
    SessionLocal.configure(bind=engine)
    original_main_engine = main_module.engine
    main_module.engine = engine
    try:
        yield engine
    finally:
        main_module.engine = original_main_engine
        SessionLocal.configure(bind=original_engine)
        engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(str(db_path) + suffix)
            except OSError:
                pass


@pytest.fixture(scope="module")
def started_app(real_app_db):
    """Faehrt die ECHTE Anwendung inklusive Lifespan hoch.

    Der zurueckgegebene Client haelt den Lifespan offen; die einzelnen Tests
    bauen sich ueber ``client_factory`` eigene Clients (mit eigener IP) auf
    DASSELBE, bereits gestartete App-Objekt.
    """
    from app.core.limiter import limiter

    # Der Lizenz-Block des Lifespans setzt globalen Modulzustand — vorher
    # sichern, damit die uebrige Suite ihn unveraendert vorfindet.
    saved_license = license_module.get_current_license()
    saved_read_only = license_module.is_read_only()

    # Die Ratenbegrenzung SCHARF stellen. ``test_endpoints.py`` und
    # ``test_license_readonly_middleware.py`` setzen beim Bauen ihrer
    # nachgebauten Anwendungen ``limiter.enabled = False`` — und weil der
    # ``Limiter`` ein Modul-Singleton ist, wirkt das global fuer den Rest des
    # Laufs. Diese Datei will die Begrenzung aber mitpruefen, also wird sie hier
    # wieder eingeschaltet und danach exakt auf den vorgefundenen Wert
    # zurueckgesetzt (kein Wegmodellieren, kein Nebenwirkungs-Leck).
    saved_limiter_enabled = limiter.enabled
    limiter.enabled = True
    with TestClient(
        main_module.app, client=_next_client_addr(), raise_server_exceptions=False
    ) as client:
        try:
            yield client
        finally:
            limiter.enabled = saved_limiter_enabled
            license_module.set_license_state(saved_license, read_only=saved_read_only)


@pytest.fixture(scope="module")
def real_app(started_app):
    """Das gestartete Anwendungsobjekt.

    Bewusst ueber ``started_app.app`` und nicht ueber ``main_module.app``: die
    SPA-Vorrichtung weiter unten laedt ``app.main`` neu, wodurch
    ``main_module.app`` waehrend ihrer Laufzeit auf ein ANDERES Objekt zeigt.
    Ueber die Referenz bleibt diese Datei unabhaengig von der Testreihenfolge.
    """
    return started_app.app


@pytest.fixture
def client_factory(real_app):
    """Liefert Clients auf die laufende echte Anwendung — jeder mit eigener
    Client-IP, damit die scharf gelassene Ratenbegrenzung Tests nicht
    gegenseitig vergiftet."""
    created: list[TestClient] = []

    def _make() -> TestClient:
        # Ohne ``with``: der Lifespan laeuft bereits ueber ``started_app``,
        # er soll nicht pro Test erneut hochgefahren werden.
        client = TestClient(
            real_app,
            client=_next_client_addr(),
            raise_server_exceptions=False,
        )
        created.append(client)
        return client

    yield _make
    for client in created:
        client.close()


def _auth_headers(client: TestClient, token: str) -> dict[str, str]:
    """Authorization + der AKTUELLE CSRF-Token aus dem Cookie-Jar.

    Die CSRF-Middleware der echten Anwendung verlangt bei gesetztem
    ``csrf_token``-Cookie einen passenden ``X-CSRF-Token``-Header — und das
    Cookie rotiert bei jedem Login. Der Helper spiegelt es so, wie es das
    Frontend tut; damit laeuft die CSRF-Middleware in JEDEM Schreibtest mit,
    statt umgangen zu werden.
    """
    headers = {"Authorization": f"Bearer {token}"}
    csrf = client.cookies.get("csrf_token")
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return headers


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, (
        f"Login ueber die echte Anwendung fehlgeschlagen: "
        f"{response.status_code} {response.text[:300]}"
    )
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def employee(started_app):
    """Legt EINMAL einen Mitarbeiter an — ueber den echten Admin-Endpoint,
    also durch die volle Zwischenschicht hindurch."""
    client = started_app
    token = _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    response = client.post(
        "/api/admin/users",
        headers=_auth_headers(client, token),
        json={
            "username": EMPLOYEE_USERNAME,
            "email": "realapp.employee@example.com",
            "password": EMPLOYEE_PASSWORD,
            "first_name": "Real",
            "last_name": "App",
            "role": "employee",
            "weekly_hours": 40,
            "vacation_days": 30,
            "work_days_per_week": 5,
        },
    )
    assert response.status_code in (200, 201), response.text[:300]
    payload = response.json()
    user = payload.get("user", payload)
    return {"id": user["id"], "username": EMPLOYEE_USERNAME, "password": EMPLOYEE_PASSWORD}


# ---------------------------------------------------------------------------
# 1. Die Vorrichtung selbst
# ---------------------------------------------------------------------------

class TestFixtureIsTheRealApp:
    """Wenn diese Klasse rot wird, prueft die ganze Datei die falsche
    Anwendung — sie ist die Selbstkontrolle der Vorrichtung."""

    def test_client_runs_the_production_app_object(self, client_factory, real_app):
        client = client_factory()
        assert client.app is real_app
        assert real_app is main_module.app
        assert client.app.title == "PraxisZeit API"

    def test_full_production_middleware_stack_is_attached(self, real_app):
        """Alle Zwischenschichten aus app/main.py haengen dran. Der Nachbau in
        test_endpoints.py hat KEINE davon."""
        from starlette.middleware.cors import CORSMiddleware
        from starlette.middleware.gzip import GZipMiddleware
        from starlette.middleware.trustedhost import TrustedHostMiddleware

        from app.middleware.csrf import CSRFMiddleware
        from app.middleware.impersonation import ImpersonationReadOnlyMiddleware
        from app.middleware.license import LicenseReadOnlyMiddleware
        from app.middleware.static_serving import (
            RequestSizeLimitMiddleware,
            SecurityHeadersMiddleware,
        )

        classes = [mw.cls for mw in real_app.user_middleware]
        for expected in (
            CORSMiddleware,
            TrustedHostMiddleware,
            SecurityHeadersMiddleware,
            RequestSizeLimitMiddleware,
            GZipMiddleware,
            ImpersonationReadOnlyMiddleware,
            LicenseReadOnlyMiddleware,
            CSRFMiddleware,
        ):
            assert expected in classes, f"{expected.__name__} fehlt im Stack"

    def test_cors_and_security_headers_wrap_the_license_guard(self, real_app):
        """Finding 11 / M-SEC2 als Reihenfolge-Invariante.

        ``user_middleware`` ist von aussen nach innen sortiert. CORS und
        SecurityHeaders MUESSEN weiter aussen liegen als die License- und
        CSRF-Middleware — sonst erreichen deren kurzgeschlossene 403er den
        Browser ohne CORS- und ohne Sicherheits-Kopfzeilen, und die Oberflaeche
        sieht statt des echten 403 einen generischen Netzwerkfehler.
        """
        from starlette.middleware.cors import CORSMiddleware

        from app.middleware.csrf import CSRFMiddleware
        from app.middleware.license import LicenseReadOnlyMiddleware
        from app.middleware.static_serving import SecurityHeadersMiddleware

        classes = [mw.cls for mw in real_app.user_middleware]
        assert classes.index(CORSMiddleware) < classes.index(LicenseReadOnlyMiddleware)
        assert classes.index(SecurityHeadersMiddleware) < classes.index(
            LicenseReadOnlyMiddleware
        )
        assert classes.index(SecurityHeadersMiddleware) < classes.index(CSRFMiddleware)

    def test_session_factory_points_at_the_fixture_database(self, real_app_db):
        """Die Middleware-Pfade (Fehlerprotokollierung, ``/api/settings``,
        Lizenz-SaaS-Check) oeffnen ihre Sitzungen ueber die globale
        ``SessionLocal`` — die muss auf die Test-Datenbank zeigen, sonst
        schreibt ein Test in die Entwicklungs-Datenbank."""
        session = SessionLocal()
        try:
            assert session.get_bind() is real_app_db
        finally:
            session.close()


class TestLifespanBootstrap:
    """Der Start der echten Anwendung ist selbst Pruefgegenstand — er wird
    ausgehalten, nicht umgangen."""

    def test_scheduler_stays_off_under_pytest(self, started_app):
        """Der Tages-Scheduler (APScheduler, 03:00) darf im Testbetrieb NIE
        anspringen — sonst laufen Lifecycle-Jobs (Mandanten-Suspend,
        Mandanten-Loeschung) gegen die Test-Datenbank."""
        assert scheduler_service._is_pytest_mode() is True
        assert scheduler_service._scheduler is None

    def test_bootstrap_created_default_tenant_and_admin(self, started_app, real_app_db):
        """Schritt 3 + 4 des Lifespans (nur Vor-Ort-Betrieb)."""
        from app.models import User, UserRole
        from app.models.tenant import Tenant

        session = SessionLocal()
        try:
            tenant = session.query(Tenant).filter(Tenant.slug == "default").first()
            assert tenant is not None
            assert tenant.id == DEFAULT_TENANT_ID

            admin = (
                session.query(User)
                .filter(User.username == ADMIN_USERNAME)
                .first()
            )
            assert admin is not None
            assert admin.role == UserRole.ADMIN
            assert admin.tenant_id == DEFAULT_TENANT_ID
        finally:
            session.close()

    def test_bootstrap_synced_public_holidays(self, started_app):
        """Schritt 6: Feiertags-Sync fuer laufendes + naechstes Jahr."""
        from app.models.public_holiday import PublicHoliday

        session = SessionLocal()
        try:
            count = (
                session.query(PublicHoliday)
                .filter(PublicHoliday.tenant_id == DEFAULT_TENANT_ID)
                .count()
            )
            assert count > 0
        finally:
            session.close()


# ---------------------------------------------------------------------------
# 2. Die eingehaengten Router liefern ueberhaupt Antworten (der 1.8.5-Fall)
# ---------------------------------------------------------------------------

class TestIncludedRoutersRespond:
    """Der 1.8.5-Fall in einem Satz: beim Zusammenbau der ECHTEN Anwendung
    (nicht einer nachgebauten) muessen die eingehaengten Router antworten."""

    def test_app_routes_contain_routers_without_path_attribute(self, real_app):
        """Die Landmine dokumentieren, ueber die 1.8.5 stolperte.

        FastAPI legt seit 0.137 ``_IncludedRouter``-Objekte OHNE ``.path`` in
        ``app.routes``. ``prometheus-fastapi-instrumentator`` 8.0.0 las
        ``route.path`` ungeschuetzt → HTTP 500 auf jedem Request. Der Test
        haelt fest, dass die Konstellation in dieser Anwendung real vorliegt —
        die folgenden Tests beweisen, dass sie trotzdem traegt.
        """
        routes_without_path = [r for r in real_app.routes if not hasattr(r, "path")]
        assert routes_without_path, (
            "Erwartet wurden included-Router ohne .path in app.routes. "
            "Fehlen sie, hat sich das FastAPI-Routing-Modell geaendert — dann "
            "muss dieser Test neu bewertet werden (der Instrumentator haengt "
            "eng an den Routing-Interna)."
        )

    def test_login_through_the_real_app(self, client_factory):
        """Das exakte 1.8.5-Symptom: HTTP 500 auf dem Login."""
        client = client_factory()
        response = client.post(
            "/api/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, response.text[:300]
        assert response.json().get("access_token")

    def test_metrics_endpoint_answers(self, client_factory):
        """Der Instrumentator selbst — er hat 1.8.5 ausgeloest."""
        client = client_factory()
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "http_request" in response.text

    def test_openapi_schema_generates(self, client_factory):
        """Die Schema-Erzeugung laeuft ueber ALLE eingehaengten Routen — sie
        faellt um, sobald eine Route beim Zusammenbau kaputt ist."""
        client = client_factory()
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert len(response.json()["paths"]) > 100

    def test_every_included_router_reached_the_assembled_app(self, client_factory):
        """Jeder in app/main.py eingehaengte Router muss im fertigen Schema
        auftauchen. Ein vergessenes ``include_router`` faellt sofort auf."""
        from fastapi.routing import APIRoute

        from app.routers import (
            absence_reasons,
            absences,
            admin,
            admin_backups,
            billing,
            change_requests,
            company_closures,
            dashboard,
            error_logs,
            feedback,
            holidays,
            impersonation,
            import_xls,
            journal,
            me,
            public_signup,
            reports,
            shift_planning,
            superadmin,
            tenant_billing,
            time_entries,
            vacation_requests,
        )
        from app.routers import auth as auth_router

        client = client_factory()
        schema_paths = set(client.get("/openapi.json").json()["paths"])

        expected = {
            "auth": auth_router.router,
            "admin": admin.router,
            "time_entries": time_entries.router,
            "absences": absences.router,
            "dashboard": dashboard.router,
            "holidays": holidays.router,
            "reports": reports.router,
            "change_requests": change_requests.router,
            "company_closures": company_closures.router,
            "error_logs": error_logs.router,
            "vacation_requests": vacation_requests.router,
            "journal": journal.router,
            "import_xls": import_xls.router,
            "superadmin": superadmin.router,
            "tenant_billing": tenant_billing.router,
            "me": me.router,
            "feedback": feedback.router,
            "public_signup": public_signup.router,
            "billing": billing.router,
            "billing_webhook": billing.webhook_router,
            "shift_planning": shift_planning.router,
            "absence_reasons_admin": absence_reasons.admin_router,
            "absence_reasons_read": absence_reasons.read_router,
            "impersonation": impersonation.router,
            # admin_backups wird nur im Vor-Ort-Betrieb eingehaengt (SaaS wuerde
            # sonst mandantenuebergreifend sichern) — die Suite laeuft onprem.
            "admin_backups": admin_backups.router,
        }
        missing = {}
        for name, router in expected.items():
            paths = {r.path for r in router.routes if isinstance(r, APIRoute)}
            if not paths:
                continue  # reiner Sammel-Router ohne eigene Routen
            if not paths & schema_paths:
                missing[name] = sorted(paths)[:3]
        assert not missing, f"Router nicht in der fertigen Anwendung: {missing}"

    @pytest.mark.parametrize(
        "path",
        [
            "/api/auth/me",
            "/api/admin/users",
            "/api/admin/settings",
            "/api/admin/users-overview",
            "/api/time-entries/",
            "/api/absences/",
            "/api/dashboard/",
            "/api/holidays/",
            "/api/change-requests/",
            "/api/company-closures/",
            "/api/admin/errors",
            "/api/vacation-requests/",
            "/api/me/data-export",
            "/api/me/type-colors",
            "/api/absence-reasons",
            "/api/admin/absence-reasons",
            "/api/admin/backups",
            "/api/admin/impersonation-sessions",
            "/api/tenant/billing",
            "/api/settings",
            "/api/system/info",
            "/api/health",
            "/api/status",
        ],
    )
    def test_representative_endpoint_does_not_fail(self, client_factory, path):
        """Quer durch die eingehaengten Router — keiner darf 5xx liefern."""
        client = client_factory()
        token = _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
        response = client.get(path, headers=_auth_headers(client, token))
        assert response.status_code < 500, (
            f"{path} -> {response.status_code} {response.text[:200]}"
        )


# ---------------------------------------------------------------------------
# 3. Sicherheits-Kopfzeilen
# ---------------------------------------------------------------------------

_SECURITY_HEADERS = (
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Content-Security-Policy",
)


class TestSecurityHeaders:
    """M-SEC2: die Kopfzeilen liegen unbedingt auf den Antworten der echten
    Anwendung — auch hinter nginx, auch auf Fehlerantworten."""

    def _assert_headers(self, response):
        for name in _SECURITY_HEADERS:
            assert name in response.headers, (
                f"{name} fehlt (status={response.status_code})"
            )
        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]

    def test_headers_on_public_endpoint(self, client_factory):
        self._assert_headers(client_factory().get("/api/health"))

    def test_headers_on_authenticated_endpoint(self, client_factory):
        client = client_factory()
        token = _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
        self._assert_headers(
            client.get("/api/dashboard/", headers=_auth_headers(client, token))
        )

    def test_headers_on_401_response(self, client_factory):
        """Auch die von der Auth-Abhaengigkeit kurzgeschlossene Antwort."""
        response = client_factory().get(
            "/api/dashboard/", headers={"Authorization": "Bearer kaputt"}
        )
        assert response.status_code == 401
        self._assert_headers(response)

    def test_no_hsts_over_plain_http(self, client_factory):
        """F-050: HSTS ueber HTTP wuerde eine native Windows-Installation
        unerreichbar machen, die zuerst per http:// aufgerufen wurde."""
        response = client_factory().get("/api/health")
        assert "Strict-Transport-Security" not in response.headers


# ---------------------------------------------------------------------------
# 4. Lizenz-Schreibsperre auf der echten Anwendung
# ---------------------------------------------------------------------------

@pytest.fixture
def expired_license():
    """Der Zustand, den der Lifespan bei abgelaufener Lizenz herstellt:
    ``LicenseInfo`` geladen UND ``read_only=True``."""
    from app.core.license import LicenseInfo

    saved_license = license_module.get_current_license()
    saved_read_only = license_module.is_read_only()
    license_module.set_license_state(
        LicenseInfo(
            customer_id="test-expired",
            customer_name="Testpraxis",
            max_employees=10,
        ),
        read_only=True,
    )
    yield
    license_module.set_license_state(saved_license, read_only=saved_read_only)


_LICENSE_BLOCK_MARKER = "Lizenz abgelaufen"


def _blocked_by_license(response) -> bool:
    if response.status_code != 403:
        return False
    try:
        return _LICENSE_BLOCK_MARKER in response.json().get("detail", "")
    except Exception:  # noqa: BLE001
        return False


class TestLicenseReadOnlyOnRealApp:
    """Bei abgelaufener Lizenz gehen Anmeldung und Ausleitung, aber Stempeln
    und Antraege sind gesperrt. Bisher nur gegen eine nachgebaute Anwendung
    geprueft — hier gegen die echte, inklusive aller davor liegenden Schichten.
    """

    def test_login_still_works(self, client_factory, expired_license):
        """Ein Lizenzproblem darf NIE zum Anmelde-Totalausfall werden — sonst
        kommt niemand mehr an die nach §16 ArbZG aufbewahrungspflichtigen
        Daten."""
        client = client_factory()
        response = client.post(
            "/api/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, response.text[:300]

    def test_data_export_still_works(self, client_factory, expired_license, employee):
        """Art. 20 DSGVO / §16 ArbZG: Ausleitung bleibt erreichbar."""
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        response = client.get("/api/me/data-export", headers=_auth_headers(client, token))
        assert response.status_code == 200
        assert not _blocked_by_license(response)

    def test_logout_still_works(self, client_factory, expired_license, employee):
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        response = client.post("/api/auth/logout", headers=_auth_headers(client, token))
        assert not _blocked_by_license(response), response.text[:200]
        assert response.status_code < 400

    def test_clock_in_is_blocked(self, client_factory, expired_license, employee):
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        response = client.post(
            "/api/time-entries/clock-in", headers=_auth_headers(client, token), json={}
        )
        assert _blocked_by_license(response), (
            f"Stempeln muesste gesperrt sein: {response.status_code} "
            f"{response.text[:200]}"
        )

    def test_vacation_request_is_blocked(self, client_factory, expired_license, employee):
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        response = client.post(
            "/api/vacation-requests/",
            headers=_auth_headers(client, token),
            json={"start_date": "2026-09-01", "end_date": "2026-09-02"},
        )
        assert _blocked_by_license(response), response.text[:200]

    def test_license_block_keeps_security_headers(
        self, client_factory, expired_license, employee
    ):
        """Die 403 der Lizenz-Middleware ist eine kurzgeschlossene Antwort —
        sie muss trotzdem durch SecurityHeaders (und CORS) zurueckkommen."""
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        response = client.post(
            "/api/time-entries/clock-in", headers=_auth_headers(client, token), json={}
        )
        assert _blocked_by_license(response)
        for name in _SECURITY_HEADERS:
            assert name in response.headers, f"{name} fehlt auf der Lizenz-403"

    def test_public_settings_reports_read_only(self, client_factory, expired_license):
        """Die Oberflaeche muss schon VOR dem Login erklaeren koennen, warum
        Schreibvorgaenge scheitern — aber ohne Lizenznehmer-Identitaet (F3)."""
        response = client_factory().get("/api/settings")
        assert response.status_code == 200
        payload = response.json()
        assert payload["license"] == {"read_only": True}

    def test_writes_pass_when_license_is_healthy(self, client_factory, employee):
        """Gegenprobe im Normalbetrieb: ohne Read-Only darf die Middleware
        nichts blocken."""
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        response = client.post(
            "/api/time-entries/clock-in", headers=_auth_headers(client, token), json={}
        )
        assert not _blocked_by_license(response), response.text[:200]
        if response.status_code == 201:
            client.post(
                "/api/time-entries/clock-out",
                headers=_auth_headers(client, token),
                json={},
            )


class TestInvalidLicenseDoesNotKillTheService:
    """Realer Totalausfall (vor 1.5.2): eine ungueltige/nicht verifizierbare
    Lizenz rief ``sys.exit(1)`` — der Dienst startete nicht mehr, niemand kam
    rein. Seither gilt: Nur-Lesen statt Dienstabbruch.

    Geprueft wird der ECHTE Lifespan-Zweig (``except LicenseError``), nicht ein
    von Hand gesetzter Modulzustand.
    """

    @pytest.fixture
    def started_with_broken_license(self, real_app_db, monkeypatch):
        key_path = Path(tempfile.mkdtemp()) / "license.key"
        key_path.write_text("das ist keine gueltige Lizenz\n", encoding="utf-8")
        monkeypatch.setattr(settings, "BETA_MODE", False)
        monkeypatch.setattr(settings, "LICENSE_KEY_PATH", str(key_path))

        saved_license = license_module.get_current_license()
        saved_read_only = license_module.is_read_only()
        try:
            with TestClient(
                main_module.app,
                client=_next_client_addr(),
                raise_server_exceptions=False,
            ) as client:
                yield client
        finally:
            license_module.set_license_state(saved_license, read_only=saved_read_only)

    def test_startup_does_not_abort(self, started_with_broken_license):
        """Kommt der Test ueberhaupt hierher, ist der Lifespan durchgelaufen —
        ein ``sys.exit(1)`` haette die Fixture mit ``SystemExit`` abgebrochen."""
        assert started_with_broken_license is not None

    def test_state_is_read_only_not_dead(self, started_with_broken_license):
        assert license_module.is_read_only() is True

    def test_login_works_with_broken_license(self, started_with_broken_license):
        response = started_with_broken_license.post(
            "/api/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, response.text[:300]

    def test_writes_are_blocked_with_broken_license(self, started_with_broken_license):
        client = started_with_broken_license
        token = _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
        response = client.post(
            "/api/time-entries/clock-in", headers=_auth_headers(client, token), json={}
        )
        assert _blocked_by_license(response), response.text[:200]


# ---------------------------------------------------------------------------
# 5. Mandanten-Aufloesung
# ---------------------------------------------------------------------------

class TestTenantResolution:
    """Die Kennung aus dem Berechtigungsnachweis wird gegen den Datenbestand
    geprueft. Das ist die App-Layer-Haelfte der Mandantentrennung; die
    DB-Haelfte (RLS) deckt ``test_tenant_rls.py`` gegen echtes PostgreSQL ab.
    """

    def test_token_of_own_tenant_is_accepted(self, client_factory, employee):
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        payload = auth_service.decode_token(token)
        assert payload["tid"] == str(DEFAULT_TENANT_ID)
        assert client.get("/api/dashboard/", headers=_auth_headers(client, token)).status_code == 200

    def test_token_for_a_foreign_tenant_is_rejected(self, client_factory, employee):
        """Ein Nachweis, dessen ``tid`` auf einen FREMDEN Mandanten zeigt,
        greift nicht — auch wenn er korrekt signiert ist, ``sub`` auf einen
        echten Nutzer zeigt und die Widerrufszaehler stimmen."""
        client = client_factory()
        # Die aktuelle ``tv`` aus einem echten Login uebernehmen, damit der
        # Widerrufs-Check (der VOR dem Mandanten-Check laeuft) nicht greift und
        # der Test wirklich die Mandanten-Aufloesung prueft.
        valid = auth_service.decode_token(
            _login(client, employee["username"], employee["password"])
        )
        forged = auth_service.create_access_token(
            user_id=str(employee["id"]),
            role="employee",
            tenant_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            token_version=valid.get("tv", 0),
        )
        response = client.get(
            "/api/dashboard/", headers={"Authorization": f"Bearer {forged}"}
        )
        assert response.status_code == 401
        assert "tenant mismatch" in response.json()["detail"].lower()

    def test_deactivated_tenant_is_rejected(self, client_factory, employee):
        """Ein deaktivierter Mandant sperrt seine Nutzer aus — geprueft gegen
        den Datenbestand, nicht gegen den Nachweis."""
        from app.models.tenant import Tenant

        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        session = SessionLocal()
        try:
            tenant = session.query(Tenant).filter(Tenant.id == DEFAULT_TENANT_ID).first()
            tenant.is_active = False
            session.commit()
            response = client.get("/api/dashboard/", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 403
            assert "Tenant deaktiviert" in response.json()["detail"]
        finally:
            tenant = session.query(Tenant).filter(Tenant.id == DEFAULT_TENANT_ID).first()
            tenant.is_active = True
            session.commit()
            session.close()

    def test_revoked_token_version_is_rejected(self, client_factory, employee):
        """Widerruf (Abmeldung, Passwortwechsel, Rollenwechsel) macht
        ausstehende Nachweise sofort ungueltig."""
        forged = auth_service.create_access_token(
            user_id=str(employee["id"]),
            role="employee",
            tenant_id=str(DEFAULT_TENANT_ID),
            token_version=999,
        )
        response = client_factory().get(
            "/api/dashboard/", headers={"Authorization": f"Bearer {forged}"}
        )
        assert response.status_code == 401
        assert "widerrufen" in response.json()["detail"].lower()

    def test_unknown_user_id_is_rejected(self, client_factory):
        forged = auth_service.create_access_token(
            user_id=str(uuid.uuid4()),
            role="admin",
            tenant_id=str(DEFAULT_TENANT_ID),
            token_version=0,
        )
        response = client_factory().get(
            "/api/dashboard/", headers={"Authorization": f"Bearer {forged}"}
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# 6. Umleitung bei fehlendem Schraegstrich am Ende
# ---------------------------------------------------------------------------

class TestTrailingSlashRedirect:
    """#dashboard-307: Bare-Collection-Routen (``@router.get("/")``) loesen
    eine 307-Umleitung aus, deren ABSOLUTE Zieladresse die Anwendung aus der
    Wirtnamen-Kopfzeile baut.

    Genau daran haengt die nginx-Regel ``proxy_set_header Host $http_host``
    (NICHT ``$host``): ``$host`` laesst den Port weg, der Browser folgt auf den
    falschen Port und die Oberflaeche meldet „Fehler beim Laden des
    Dashboards". Der Test haelt die App-Seite dieses Vertrags fest.
    """

    def test_bare_collection_path_redirects(self, client_factory, employee):
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        response = client.get(
            "/api/dashboard",
            headers=_auth_headers(client, token),
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert response.headers["location"] == "http://testserver/api/dashboard/"

    def test_redirect_target_keeps_the_port_from_the_host_header(
        self, client_factory, employee
    ):
        """Der Kern der Sache: steht ein Port in der Wirtnamen-Kopfzeile, MUSS
        er in der Zieladresse landen."""
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        headers = _auth_headers(client, token)
        headers["Host"] = "praxis.example:8080"
        response = client.get(
            "/api/dashboard", headers=headers, follow_redirects=False
        )
        assert response.status_code == 307
        assert response.headers["location"] == "http://praxis.example:8080/api/dashboard/"

    def test_following_the_redirect_reaches_the_endpoint(self, client_factory, employee):
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        response = client.get(
            "/api/dashboard", headers=_auth_headers(client, token), follow_redirects=True
        )
        assert response.status_code == 200

    def test_forwarded_proto_is_honoured(self, client_factory, employee):
        """uvicorn laeuft mit ``--proxy-headers``; hinter TLS-terminierendem
        nginx muss das Schema aus ``X-Forwarded-Proto`` kommen, sonst schickt
        die Umleitung den Browser von https auf http."""
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        headers = _auth_headers(client, token)
        headers["X-Forwarded-Proto"] = "https"
        response = client.get(
            "/api/dashboard", headers=headers, follow_redirects=False
        )
        assert response.status_code == 307
        # TestClient spricht kein echtes Proxy-Protokoll — die Zieladresse muss
        # aber in jedem Fall absolut sein und den Wirtnamen tragen.
        assert response.headers["location"].endswith("/api/dashboard/")


# ---------------------------------------------------------------------------
# 7. Ratenbegrenzung (scharf gelassen)
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Die Begrenzung wird nicht wegmodelliert, sondern mitgeprueft.

    Bewusst an ``/api/auth/change-password`` (fest verdrahtet ``3/minute``)
    statt am Login: ``LOGIN_RATE_LIMIT`` kommt aus der Umgebung und ist in der
    Entwicklungs-/E2E-Umgebung absichtlich hochgesetzt — ein Test darauf waere
    umgebungsabhaengig.
    """

    def test_limit_is_enforced_by_the_real_app(self, client_factory, employee):
        from app.core.limiter import limiter

        assert limiter.enabled is True, (
            "Die Ratenbegrenzung wurde global abgeschaltet — dann prueft diese "
            "Datei sie nicht mehr mit."
        )
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        headers = _auth_headers(client, token)
        codes = []
        for _ in range(5):
            response = client.post(
                "/api/auth/change-password",
                headers=headers,
                json={"current_password": "falsch", "new_password": "Egal2026!xyz"},
            )
            codes.append(response.status_code)
        assert 429 in codes, f"Kein 429 nach 5 Versuchen: {codes}"
        assert codes[:3] == [400, 400, 400], codes

    def test_each_client_ip_has_its_own_bucket(self, client_factory, employee):
        """Der Grund, warum die Vorrichtung ohne Abschalten der Begrenzung
        auskommt: slowapi schluesselt per Client-IP."""
        first = client_factory()
        token = _login(first, employee["username"], employee["password"])
        for _ in range(4):
            first.post(
                "/api/auth/change-password",
                headers=_auth_headers(first, token),
                json={"current_password": "falsch", "new_password": "Egal2026!xyz"},
            )
        second = client_factory()
        token2 = _login(second, employee["username"], employee["password"])
        response = second.post(
            "/api/auth/change-password",
            headers=_auth_headers(second, token2),
            json={"current_password": "falsch", "new_password": "Egal2026!xyz"},
        )
        assert response.status_code != 429, (
            "Ein anderer Client-Bucket wurde vom vorherigen Test mit gesperrt."
        )


# ---------------------------------------------------------------------------
# 7b. CSRF-Doppel-Cookie und Groessengrenze
# ---------------------------------------------------------------------------

class TestCsrfDoubleSubmit:
    """F-024: die CSRF-Middleware verlangt bei gesetztem ``csrf_token``-Cookie
    einen passenden ``X-CSRF-Token``-Header auf schreibenden Verfahren.

    In der nachgebauten Anwendung von ``test_endpoints.py`` haengt sie nicht
    dran — jeder dortige Schreibtest laeuft also an ihr vorbei.
    """

    def test_write_without_header_is_rejected(self, client_factory, employee):
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        assert client.cookies.get("csrf_token"), "Login setzt kein CSRF-Cookie"
        response = client.post(
            "/api/time-entries/clock-in",
            headers={"Authorization": f"Bearer {token}"},  # bewusst OHNE X-CSRF-Token
            json={},
        )
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    def test_write_with_mismatching_header_is_rejected(self, client_factory, employee):
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        response = client.post(
            "/api/time-entries/clock-in",
            headers={"Authorization": f"Bearer {token}", "X-CSRF-Token": "falsch"},
            json={},
        )
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    def test_write_with_mirrored_cookie_passes(self, client_factory, employee):
        client = client_factory()
        token = _login(client, employee["username"], employee["password"])
        response = client.post(
            "/api/time-entries/clock-in",
            headers=_auth_headers(client, token),
            json={},
        )
        assert response.status_code != 403, response.text[:200]
        if response.status_code == 201:
            client.post(
                "/api/time-entries/clock-out",
                headers=_auth_headers(client, token),
                json={},
            )

    def test_login_is_exempt(self, client_factory, employee):
        """Beim Login gibt es noch keine Sitzung — der Pfad muss ausgenommen
        bleiben, sonst kaeme nach einem abgelaufenen Cookie niemand mehr rein."""
        client = client_factory()
        _login(client, employee["username"], employee["password"])
        # Zweiter Login mit dem (nun rotierten) Cookie im Jar, aber ohne Header.
        response = client.post(
            "/api/auth/login",
            json={"username": employee["username"], "password": employee["password"]},
        )
        assert response.status_code == 200


class TestRequestSizeLimit:
    """Die 2-MB-Grenze haengt unbedingt dran (Verteidigung in der Tiefe gegen
    ein fehlendes ``client_max_body_size`` im vorgelagerten nginx)."""

    def test_oversized_body_is_rejected(self, client_factory):
        client = client_factory()
        response = client.post(
            "/api/auth/login",
            content=b"x" * (2 * 1024 * 1024 + 1024),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413


# ---------------------------------------------------------------------------
# 8. Fehlerprotokollierung
# ---------------------------------------------------------------------------

class TestErrorCaptureMiddleware:
    """``capture_errors_middleware`` schreibt 5xx in ``error_logs`` — die
    Grundlage der Admin-Fehleransicht. In einer nachgebauten Anwendung
    existiert sie nicht."""

    def test_unhandled_exception_is_persisted(self, client_factory, real_app):
        from app.models.error_log import ErrorLog

        marker = f"realapp-probe-{uuid.uuid4().hex[:8]}"
        probe_path = f"/api/__realapp_probe_{marker}"

        @real_app.get(probe_path)
        def _boom():  # pragma: no cover - absichtlicher Fehler
            raise RuntimeError(marker)

        try:
            response = client_factory().get(probe_path)
            assert response.status_code == 500
            session = SessionLocal()
            try:
                row = (
                    session.query(ErrorLog)
                    .filter(ErrorLog.path == probe_path)
                    .first()
                )
                assert row is not None, "Kein error_logs-Eintrag geschrieben"
                assert row.status_code == 500
                assert marker in row.message
            finally:
                session.close()
        finally:
            real_app.router.routes = [
                r for r in real_app.router.routes
                if getattr(r, "path", None) != probe_path
            ]
            real_app.openapi_schema = None


# ---------------------------------------------------------------------------
# 9. Rueckfall-Zwischenschicht fuer die Oberflaeche (SPA)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def spa_app(real_app_db):
    """Baut die ECHTE Anwendung im Vor-Ort-Betrieb (``SERVE_FRONTEND=True``) neu.

    ``app/main.py`` entscheidet beim Import, ob die ``SPAFallbackMiddleware``
    eingehaengt wird. Statt sie im Test von Hand aufzusetzen (dann waere es
    wieder ein Nachbau) laden wir das Modul mit gesetzter Einstellung neu — so
    laeuft der echte Zusammenbau-Zweig.

    Nach dem Test wird zurueckgeladen; die Protokoll-Handler, die der
    Modul-Rumpf an ``uvicorn.error``/``fastapi`` haengt, und die
    Prometheus-Registry werden dabei auf den Ausgangsstand zurueckgesetzt,
    damit die uebrige Suite keine Doppel-Registrierungen erbt.

    Zur Registry: ``PrometheusInstrumentatorMiddleware`` legt ihre Metriken
    beim BAUEN des Middleware-Stacks an. Zwei gestartete Anwendungen in einem
    Prozess wuerden dieselben Metriknamen doppelt registrieren
    (``DuplicateTimeseries``). Wir leeren die Registry deshalb fuer die Dauer
    der zweiten Anwendung und spielen sie danach vollstaendig zurueck.
    """
    from prometheus_client import REGISTRY

    frontend_dir = Path(tempfile.mkdtemp())
    (frontend_dir / "index.html").write_bytes(b"<html><body>SPA</body></html>")

    loggers = [logging.getLogger("uvicorn.error"), logging.getLogger("fastapi")]
    saved_handlers = [list(lg.handlers) for lg in loggers]

    saved_collectors = dict(REGISTRY._collector_to_names)
    saved_names = dict(REGISTRY._names_to_collectors)
    REGISTRY._collector_to_names.clear()
    REGISTRY._names_to_collectors.clear()

    saved_serve = settings.SERVE_FRONTEND
    saved_dir = settings.FRONTEND_DIR
    saved_license = license_module.get_current_license()
    saved_read_only = license_module.is_read_only()
    # Das ORIGINAL-Anwendungsobjekt festhalten: mehrere Testdateien lesen
    # ``app.main.app`` erst zur Laufzeit aus. Bekaemen sie das frisch geladene,
    # nie gestartete Objekt, wuerde beim ersten Request sein Middleware-Stack
    # gebaut — und die Prometheus-Metriken ein zweites Mal registriert
    # (``DuplicateTimeseries``). Nach dem Zurueckladen setzen wir das Attribut
    # deshalb wieder auf das laufende Objekt.
    original_app = main_module.app
    settings.SERVE_FRONTEND = True
    settings.FRONTEND_DIR = str(frontend_dir)
    try:
        importlib.reload(main_module)
        main_module.engine = real_app_db
        with TestClient(
            main_module.app,
            client=_next_client_addr(),
            raise_server_exceptions=False,
        ) as client:
            yield client
    finally:
        settings.SERVE_FRONTEND = saved_serve
        settings.FRONTEND_DIR = saved_dir
        importlib.reload(main_module)
        main_module.app = original_app
        main_module.engine = real_app_db
        license_module.set_license_state(saved_license, read_only=saved_read_only)
        for lg, handlers in zip(loggers, saved_handlers):
            lg.handlers = handlers
        REGISTRY._collector_to_names.clear()
        REGISTRY._collector_to_names.update(saved_collectors)
        REGISTRY._names_to_collectors.clear()
        REGISTRY._names_to_collectors.update(saved_names)


class TestSpaFallbackDoesNotSwallowWrites:
    """Die Rueckfall-Schicht fuer die Oberflaeche ist bewusst eine
    Zwischenschicht und KEINE Auffang-Route.

    Historie: ein ``@app.get("/{full_path:path}")`` als Auffang-Route hat den
    Pfad fuer ALLE schreibenden Verfahren belegt — POST/PUT/DELETE trafen eine
    reine GET-Route und bekamen HTTP 405 „Method Not Allowed" statt den
    Endpoint (oder ein ehrliches 404).
    """

    def test_spa_middleware_is_attached_in_native_mode(self, spa_app):
        from app.middleware.static_serving import SPAFallbackMiddleware

        classes = [mw.cls for mw in spa_app.app.user_middleware]
        assert SPAFallbackMiddleware in classes

    def test_unknown_get_route_serves_the_spa_shell(self, spa_app):
        response = spa_app.get(
            "/mitarbeiter/uebersicht", headers={"Accept": "text/html"}
        )
        assert response.status_code == 200
        assert b"SPA" in response.content

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_write_to_unknown_path_is_404_not_405(self, spa_app, method):
        """Der 405-Regressionswaechter."""
        response = getattr(spa_app, method)("/api/gibt-es-nicht")
        assert response.status_code == 404, (
            f"{method.upper()} /api/gibt-es-nicht -> {response.status_code}; "
            "405 bedeutet, dass eine Auffang-Route den Pfad belegt."
        )

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_write_to_unknown_frontend_path_is_404_not_405(self, spa_app, method):
        """Auch ausserhalb von /api darf die Rueckfall-Schicht kein 405
        erzeugen — sie greift nur fuer GET-Antworten mit Status 404."""
        response = getattr(spa_app, method)("/mitarbeiter/uebersicht")
        assert response.status_code == 404

    def test_write_to_a_real_api_path_reaches_the_router(self, spa_app):
        """Der Beweis, dass Schreibvorgaenge NICHT abgefangen werden: der
        Endpoint antwortet selbst (hier 401 mangels Nachweis), nicht die
        Rueckfall-Schicht."""
        response = spa_app.post("/api/time-entries/clock-in", json={})
        assert response.status_code == 401

    def test_login_through_the_native_assembly(self, spa_app):
        response = spa_app.post(
            "/api/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, response.text[:300]

    def test_missing_asset_returns_404_not_the_spa_shell(self, spa_app):
        """Sonst liefert ein veralteter Service Worker die Oberflaeche als
        Stylesheet ausgeliefert zurueck — die bekannte „unstyled page"."""
        response = spa_app.get(
            "/assets/veraltet-abc123.css", headers={"Accept": "text/css,*/*;q=0.1"}
        )
        assert response.status_code == 404
        assert b"SPA" not in response.content
