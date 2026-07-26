# Wochenstunden anpassen — Design

**Datum:** 2026-07-26
**Status:** freigegeben
**Ziel-Version:** Folgeversion nach 1.16.0

## Problem

Admins verstehen die Wochenstunden-Änderung nicht. Im Bearbeiten-Formular steht ein
gewöhnliches Eingabefeld „Wochenstunden". Wer es überschreibt, ändert damit den
Vertragswert — und zugleich den **Rückfallwert für die gesamte Vergangenheit**, denn
`get_weekly_hours_for_date` greift für alle Tage vor der ersten erfassten Änderung auf
`user.weekly_hours` zurück. Das Soll bereits abgeschlossener Monate verschiebt sich
dadurch still.

Die dafür vorgesehene Historie liegt hinter einem separaten Uhr-Symbol in der
Benutzerliste, das niemand mit dem Feld in Verbindung bringt. Und selbst wer sie
findet, sieht dort nur „ab 15.03.2026: 20,0 Std/Woche" — dass die vorherige Stundenzahl
implizit am Vortag endet, steht nirgends.

Ergebnis: Admins ändern das Feld, wundern sich über verschobene Salden und finden die
Historie nicht.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Verhältnis zum bestehenden Verlauf-Modal | **Ein Dialog, zwei Zugänge.** Das bestehende `WorkingHoursModal` wird ausgebaut und aus Formular *und* Benutzerliste geöffnet. |
| Umfang der Rückrechnung | **Hinweis + Abwesenheiten mitziehen.** Kein Anfassen eingefrorener Jahresabschlüsse. |
| Direktes Setzen per API | **`PUT /users/{id}` lehnt `weekly_hours` mit 400 ab.** Genau ein Schreibweg. |
| Löschen einer Änderung | Rechnet die Abwesenheits-Stunden im betroffenen Fenster ebenfalls zurück (Symmetrie). |
| `track_hours = false` | Abwesenheits-Stunden bleiben unangetastet (dort zählt nur die Tageszählung). |

## Oberfläche

### UserForm

Beim **Bearbeiten** eines bestehenden Mitarbeiters:

```
Wochenstunden
┌────────┐  ┌──────────────────────┐
│ 40,0 h │  │ ✎ Wochenstunden      │
└────────┘  │   anpassen…          │
 read-only  └──────────────────────┘
```

Beim **Anlegen** bleibt das Feld ein normales Eingabefeld — es gibt noch keine Historie,
und der Startwert muss gesetzt werden können.

Bei `use_daily_schedule = true` ist der Button deaktiviert mit dem Hinweis, dass die
Stunden dort über die Tagesstunden gepflegt werden (der Endpoint lehnt diese Nutzer
bereits mit 400 ab — die Oberfläche sagt es jetzt vorher).

Das Formular sendet `weekly_hours` beim Update **nicht mehr mit**. Ohne diese Änderung
würde jedes Speichern am neuen 400 scheitern.

### WorkingHoursModal

Erreichbar über den Button im Formular und weiterhin über das Uhr-Symbol in der Liste.

- **Kopf:** aktuell gültige Stundenzahl.
- **Neue Änderung:** Stundenzahl, Datumsauswahl „Gültig ab", Notiz.
- **Verlauf:** je Eintrag `ab TT.MM.JJJJ bis TT.MM.JJJJ` statt nur `ab`. Der jüngste
  Eintrag zeigt `bis heute`. Das implizite Ende wird damit sichtbar — der Kern des
  Verständnisproblems.

### Rückwirkender Hinweis

Liegt das gewählte Datum vor heute, fragt der Dialog eine Vorschau ab und zeigt vor dem
Speichern:

```
⚠ Rückwirkende Änderung
  Zeitraum:      15.03.2026 – 26.07.2026
  Tagessoll:     8,0 h → 4,0 h
  Betroffen:     12 Abwesenheiten werden auf das neue Tagessoll umgestellt
  Hinweis:       Das Jahr 2026 ist noch nicht abgeschlossen.
```

Berührt der Zeitraum ein abgeschlossenes Jahr, erscheint zusätzlich der Hinweis, dass
dessen eingefrorener Übertrag dadurch veraltet ist und gegebenenfalls manuell zu prüfen
ist. Gespeichert wird erst nach ausdrücklicher Bestätigung.

## Backend

### Neu: Vorschau

```
GET /api/admin/users/{user_id}/working-hours-changes/preview
    ?effective_from=YYYY-MM-DD&weekly_hours=X
```

Antwort:

```json
{
  "is_retroactive": true,
  "period_start": "2026-03-15",
  "period_end": "2026-07-26",
  "current_daily_target": 8.0,
  "new_daily_target": 4.0,
  "affected_absences": 12,
  "closed_years": [2025],
  "blocked_reason": null
}
```

Rein lesend, `require_admin`, tenant-gescoped. `blocked_reason` trägt den Grund, wenn der
Endpoint die Änderung ablehnen würde (individueller Tagesplan, Datum bereits belegt) —
so kann der Dialog den Speichern-Button vorher sperren, statt den Nutzer in einen 400
laufen zu lassen.

### Anlegen (erweitert)

`POST /users/{id}/working-hours-changes` behält die bestehende Logik (Basis-Zeile bei der
ersten Änderung, `user.weekly_hours`-Nachführung, Tagesplan-Guard, Duplikat-Guard) und
bekommt danach den Rückrechnungs-Schritt:

Ist `effective_from < heute`, werden alle Abwesenheiten des Mitarbeiters im Fenster
`[effective_from, heute]` auf das neue Tagessoll des jeweiligen Tages gesetzt.

Regeln je Abwesenheit:

- **Ausgenommen `OVERTIME`** — Freizeitausgleich trägt explizit beantragte Stunden, kein
  abgeleitetes Tagessoll.
- **Ausgenommen Mitarbeitende mit `track_hours = false`** — dort zählt nur die
  Tageszählung.
- `half_day = true` → `0,5 × Tagessoll`.
- Halbtags-Sondertage (24./31.12.) über `calculation_service.half_special_day_weight`.
- Tage außerhalb des Beschäftigungsfensters (`_within_employment_window`) bleiben
  unangetastet.
- Tage ohne Soll (Wochenende, Feiertag, freier Wochentag im Tagesplan) ergeben 0 und
  werden übersprungen statt auf 0 gesetzt.

Ein **Audit-Eintrag** (`action="update"`, `source="wh_change"`, < 40 Zeichen) hält
Zeitraum und Anzahl der angepassten Abwesenheiten fest.

Die Antwort trägt zusätzlich `adjusted_absences` und – falls zutreffend – die
`stale_year_closing_warning`, damit der Dialog es zurückmelden kann.

### Löschen (erweitert)

`DELETE /users/{id}/working-hours-changes/{change_id}` rechnet nach dem Löschen dasselbe
Fenster mit dem dann gültigen Wert zurück. Ohne das bliebe nach einem versehentlich
angelegten und wieder entfernten Eintrag ein falscher Stand stehen.

### Sperre in update_user

`PUT /api/admin/users/{user_id}` weist `weekly_hours` im Payload mit **400** ab:

> „Wochenstunden werden über ‚Wochenstunden anpassen' mit Wirkungsdatum geändert, damit
> die Historie und das Soll vergangener Monate korrekt bleiben."

`POST /api/admin/users` (Anlegen) bleibt unverändert.

## Gemeinsamer Helper

Die Rückrechnung lebt an **einer** Stelle:

```python
calculation_service.retarget_absence_hours(db, user, start, end) -> int
```

Sie liefert die Anzahl angepasster Zeilen und wird von Anlegen, Löschen und der Vorschau
(dort im Trockenlauf für die Zählung) genutzt. Kein zweiter Rechenpfad — genau die
Disziplin, an der dieses Projekt zuvor mehrfach gescheitert ist (#394, #377, Export-Soll).

## Randfälle, die getestet werden

| Fall | Erwartung |
|---|---|
| Erste Änderung überhaupt | Basis-Zeile mit altem Wert wird angelegt (1.16.0-Verhalten bleibt) |
| Datum in der Zukunft | keine Rückrechnung, kein Warnhinweis |
| Datum = heute | nicht rückwirkend |
| Datum = Tag vor heute | rückwirkend, ein Tag im Fenster |
| `VACATION` im Fenster | `hours` auf neues Tagessoll; Urlaubs**tage** unverändert (Tagesprinzip) |
| `SICK` / `TRAINING` | `hours` angepasst → Ist-Gutschrift stimmt wieder |
| `OVERTIME` | unverändert |
| `half_day = true` | `0,5 ×` neues Tagessoll |
| Halbtags-Sondertag 24.12. | Sondertagsfaktor angewandt |
| Abwesenheit vor `first_work_day` | unverändert |
| Abwesenheit nach `last_work_day` | unverändert |
| Wochenende / Feiertag | übersprungen |
| `track_hours = false` | alle Abwesenheiten unverändert |
| `use_daily_schedule = true` | 400, keine Änderung |
| Doppeltes `effective_from` | 400, keine Änderung |
| Abgeschlossenes Jahr betroffen | Warnung in der Antwort, Übertrag unverändert |
| Löschen einer rückwirkenden Änderung | Stunden werden auf den dann gültigen Wert zurückgerechnet |
| `PUT users/{id}` mit `weekly_hours` | 400, Nutzer unverändert |
| `PUT users/{id}` ohne `weekly_hours` | unverändert erfolgreich |
| `POST users` mit `weekly_hours` | unverändert erfolgreich |

## Nicht Teil dieser Arbeit

- Der Windows-Wizard und die nativen Installer.
- Rückrechnung eingefrorener Jahresabschlüsse (bewusst nur Warnung).
- Änderung des Tagesplan-Modells (`use_daily_schedule`).

## Doku-Flächen

Nutzer-sichtbare Änderung → nachzuziehen sind Handbuch Admin, Cheat-Sheet Admin, beide
`frontend/public/help`-Mirrors (byte-identisch) und die In-App-Hilfe in `DocViewer.tsx`.
`docs/BERECHNUNGEN.md` erhält den Hinweis, dass die Rückrechnung die gespeicherten
Abwesenheits-Stunden mitzieht.
