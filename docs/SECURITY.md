# Security Policy

## Unterstützte Versionen

Sicherheitsupdates erscheinen ausschließlich für die jeweils aktuelle
Minor-Linie. Ältere Linien erhalten keine Backports — bitte auf die neueste
Version aktualisieren.

| Version | Unterstützt        |
| ------- | ------------------ |
| 1.12.x  | :white_check_mark: |
| < 1.12  | :x:                |

## Sicherheitslücke melden

Bitte Schwachstellen **nicht** über öffentliche GitHub-Issues melden, sondern
einen der folgenden vertraulichen Wege nutzen:

- **GitHub Security Advisories:** „Report a vulnerability" unter
  <https://github.com/phash/praxiszeit/security/advisories/new>
- **E-Mail:** m.roedig@gmail.com (gerne mit „PraxisZeit Security" im Betreff)

Bitte beschreibe die Lücke, betroffene Version/Komponente und – wenn möglich –
einen Reproduktionsweg. Eine erste Rückmeldung erfolgt in der Regel innerhalb
weniger Werktage; nach Bestätigung wird zeitnah ein Fix bereitgestellt und die
gemeldete Person (auf Wunsch) in der Release-Notiz genannt.

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

