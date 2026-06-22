# Security Policy

## Supported Versions

Use this section to tell people about which versions of your project are
currently being supported with security updates.

| Version | Supported          |
| ------- | ------------------ |
| 5.1.x   | :white_check_mark: |
| 5.0.x   | :x:                |
| 4.0.x   | :white_check_mark: |
| < 4.0   | :x:                |

## Reporting a Vulnerability

Use this section to tell people how to report a vulnerability.

Tell them where to go, how often they can expect to get an update on a
reported vulnerability, what to expect if the vulnerability is accepted or
declined, etc.

## API-Konvention: 404 statt 403 bei fremden Ressourcen (#120)

Greift ein Nutzer auf eine Ressource zu, die zwar in seinem Tenant existiert,
aber **einem anderen Nutzer gehört** (Owner-Check schlägt fehl), antwortet die
API mit **404 „nicht gefunden"** — nicht mit 403 — und mit **derselben Meldung**
wie bei einer unbekannten ID. So verrät der Response-Code nicht die Existenz
einer fremden Ressourcen-ID im eigenen Tenant (kein Enumeration-Oracle, RFC-7235-
konform; konsistent mit den Admin-Endpoints, die foreign-Tenant ebenfalls 404
geben). Betrifft die Owner-Checks in `vacation_requests.py`, `absences.py` und
`change_requests.py`.

**Weiterhin 403** (kein Existenz-Leak) bei reinen **Rollen-/Rechte-Checks**, die
keine konkrete fremde Ressource referenzieren — z. B. ein Nicht-Admin, der über
einen Query-Parameter fremde Daten filtern oder eine Ressource für einen anderen
Nutzer anlegen will (`require_admin`, `absences.py`-`user_id`-Filter/-Anlage).

