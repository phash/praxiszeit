# Design: Minijob-Compliance — Mindestlohn + § 2 Abs. 2 MiLoG (#377, Baustein 1 + 3)

**Issue:** [#377](https://github.com/phash/praxiszeit/issues/377) — Minijob mit Monatsstunden
**Datum:** 2026-07-08
**Status:** Implementiert (Branch `feat/377-minijob-milog`) — Backend+Frontend+Doku, Tests grün, Migration 062 verifiziert. Modellentscheidungen § 7 verbindlich; die Pseudocodes in §§ 3.3/3.4 sind durch § 7 + `milog_service.py` ersetzt (dort Source of Truth).

> **§ 7 unten** enthält die verbindlichen Modellentscheidungen aus dem 8-Lens-Adversarial-Review — sie **überschreiben** abweichende Formulierungen in §§ 3.3/3.4.
**Umfang:** Baustein **1** (Mindestlohn anzeigen) + **3** (§ 2 Abs. 2 MiLoG: 50-%-Prüfung **und** 12-Monats-Ausgleichsfrist). Baustein **2** (Wochen↔Monat-Umschaltung / Monatsmodus) ist **separat/später** und NICHT Teil dieser Spec.

---

## 1. Problem & Kontext

Eine Minijobberin arbeitet „auf Arbeitszeitkonto (sonstige flexible Arbeitszeit­regelung)": festes Monatsentgelt, **vertraglich 33 h/Monat**, Schwankungen laufen über das Konto. PraxisZeit kann heute nur **Wochenstunden** erfassen und prüft die MiLoG-Arbeitszeitkonto-Grenzen nicht.

### Verifizierte Rechtslage (Primärquellen, Stand 2026)

- **Mindestlohn:** 13,90 €/h ab 01.01.2026, 14,60 €/h ab 01.01.2027 (Mindestlohnkommission, Beschluss 27.06.2025). [BMAS], [§ 1 MiLoG].
- **Geringfügigkeitsgrenze:** 603 €/Monat ab 01.01.2026 (= `Mindestlohn × 130 ÷ 3`, ≙ 10 Wochenstunden). Jahresgrenze 7.236 €.
- **§ 2 Abs. 2 MiLoG (wörtlich):** *„Die auf das Arbeitszeitkonto eingestellten Arbeitsstunden dürfen monatlich jeweils 50 Prozent der vertraglich vereinbarten Arbeitszeit nicht übersteigen"*; Ausgleich (Freizeit/Zahlung) **binnen 12 Kalendermonaten** nach monatlicher Erfassung, bei Beendigung im Folgemonat. [gesetze-im-internet.de/milog/__2.html]
- **Minijob-Grenze-Überschreiten:** gelegentlich-unvorhergesehen max. 2 Kalendermonate/Zeitjahr, bis 1.206 € (2× Grenze). Keine Jahresdurchschnitts-Betrachtung. (Nicht Teil dieser Spec — braucht Lohn/Verdienst-Logik.)

### Warum ohne Baustein 2 machbar

Die 50-%-Regel bezieht sich auf die **vertraglich vereinbarte Arbeitszeit**. Ohne Monatsmodus leiten wir die vereinbarte Monatszeit aus den vorhandenen `weekly_hours` ab: `Monat = Woche × 13/3` (52 Wochen ÷ 12 Monate = 4,333…). Baustein 2 liefert später eine direkt vereinbarte Monatszahl; dann wird diese Ableitung durch den echten Wert ersetzt.

---

## 2. Umfang

1. **Mindestlohn-Anzeige** — datumsabhängige, gesetzlich fixe Konstante, angezeigt (kein Rechenkern).
2. **§ 2 Abs. 2 — 50-%-Prüfung (3a)** — pro Monat: Konto-Plusstunden > 50 % der vereinbarten Monatszeit → **weiche** Warnung. Sichtbar **beim Ausstempeln** (month-to-date) **und** in Monatsreport + Überstundenkonto.
3. **§ 2 Abs. 2 — 12-Monats-Ausgleichsfrist (3b)** — FIFO-Aging der Konto-Bewegungen: ältester offener Posten ≥ 12 Monate = überfällig, ≥ 10 = bald fällig → weiche Warnung im Überstundenkonto + Monatsreport.

Alle Prüfungen laufen **nur** für Nutzer mit dem neuen Opt-in-Flag. **Nichts blockiert** (weiche Warnungen, wie ArbZG).

---

## 3. Detaildesign

### 3.1 Datenmodell

`User.milog_working_time_account` — `Boolean`, `nullable=False`, `default=False`, `server_default='false'`. Bezeichnung „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)". Muster wie `exempt_from_arbzg`/`is_night_worker`. Eine Migration. **Keine Lohndaten** (einfache Variante).

### 3.2 Mindestlohn (Baustein 1)

Neues Modul `backend/app/core/minimum_wage.py`:

```python
from datetime import date
from decimal import Decimal

# Gesetzlich fixierte Stufen (aufsteigend). Neue Stufe VORNE einpflegen, wenn
# beschlossen — NIE Werte raten. Quelle: Mindestlohnkommission / § 1 MiLoG.
_MINIMUM_WAGE_STEPS = [
    (date(2025, 1, 1), Decimal("12.82")),
    (date(2026, 1, 1), Decimal("13.90")),
    (date(2027, 1, 1), Decimal("14.60")),
]

def minimum_wage_for(d: date) -> Decimal:
    """Gültiger gesetzlicher Mindestlohn (€/h) zum Datum d."""
    applicable = _MINIMUM_WAGE_STEPS[0][1]
    for eff, val in _MINIMUM_WAGE_STEPS:
        if d >= eff:
            applicable = val
    return applicable

def current_minimum_wage(today: date) -> Decimal:
    return minimum_wage_for(today)

def minimum_wage_info(today: date) -> dict:
    """{current, since, next|None} für die Anzeige."""
    current, since = _MINIMUM_WAGE_STEPS[0][1], _MINIMUM_WAGE_STEPS[0][0]
    nxt = None
    for eff, val in _MINIMUM_WAGE_STEPS:
        if today >= eff:
            current, since = val, eff
        elif nxt is None:
            nxt = {"value": float(val), "from": eff.isoformat()}
    return {"current": float(current), "since": since.isoformat(), "next": nxt}
```

- `today` wird über `timezone_service.today_local()` reingereicht (kein `date.today()` direkt — Testbarkeit/TZ).
- **Ausgabe:** `/api/system/info` (public, existiert in `main.py::system_info`) erhält `minimum_wage: minimum_wage_info(today_local())`. Nie 500 (rein statisch).
- **Frontend:** `systemStore` liest `minimum_wage`; Anzeige in `Settings.tsx` (Compliance-Karte) + `UserForm` neben dem Flag (aktueller Wert + „seit …" + ggf. „ab … dann …").

### 3.3 § 2 Abs. 2 — 50-%-Prüfung (3a)

Neues `backend/app/services/milog_service.py`:

```python
AGREED_MONTHLY_FACTOR = Decimal(13) / Decimal(3)  # Woche → Monat (52/12)

def agreed_monthly_hours(db, user, ref_date) -> Decimal:
    """Vertraglich vereinbarte Monatszeit = Wochenstunden(zum Datum) × 13/3.
    (Baustein 2 ersetzt das später durch eine direkt vereinbarte Monatszahl.)"""
    weekly = calculation_service.get_weekly_hours_for_date(db, user, ref_date)
    return Decimal(str(weekly)) * AGREED_MONTHLY_FACTOR

def account_hours_in_month(db, user, year, month) -> Decimal:
    """Auf das Konto eingestellte Plusstunden des Monats = max(0, Ist−Soll)."""
    bal = calculation_service.get_monthly_balance(db, user, year, month)  # Ist − Soll
    return max(Decimal('0'), Decimal(str(bal)))

def milog_50_check(db, user, year, month, up_to_date=None):
    """None, wenn Flag aus oder ≤ 50 %. Sonst dict mit Zahlen für die Warnung.
    up_to_date: month-to-date beim Ausstempeln; None = ganzer Monat."""
    if not user.milog_working_time_account:
        return None
    agreed = agreed_monthly_hours(db, user, date(year, month, 1))
    cap = agreed / 2
    account = account_hours_in_month(db, user, year, month)  # ggf. up_to_date-Variante
    if account > cap:
        return {"account_hours": float(account), "cap": float(cap),
                "agreed_monthly": float(agreed)}
    return None
```

> `get_monthly_balance(db, user, year, month)` — reale Signatur in Task-Zeit prüfen (calculation_service.py:478); ggf. `up_to_date`-Parameter für month-to-date beim Ausstempeln nutzen.

**Warncode:** `MILOG_ACCOUNT_50: Konto-Plusstunden dieses Monats (X.Xh) über 50 % der vereinbarten Monatszeit (Cap Y.Yh, §2 Abs.2 MiLoG).`

**Surfaces:**
- `clock_out` (`time_entries.py`): nur wenn Flag → `milog_50_check(... up_to_date=today)` → Code an die bestehende `clock_out`-`warnings`-Liste.
- Monatsreport (`/admin/reports/monthly`) + Überstundenkonto: dieselbe Prüfung, Warnung/Badge je betroffenen Monat/MA.

### 3.4 § 2 Abs. 2 — 12-Monats-Ausgleichsfrist (3b)

```python
def settlement_aging(db, user, as_of):
    """FIFO über die Monats-Deltas des Überstundenkontos: Plus-Deltas =
    Einzahlungen (monatsstamped), Minus-Deltas = Ausgleich (verbraucht älteste
    zuerst). Liefert den ältesten noch offenen Einzahlungsmonat + dessen Alter.
    None, wenn Flag aus oder kein offener Posten."""
    if not user.milog_working_time_account:
        return None
    history = calculation_service.get_overtime_history(db, user)  # [(year, month, delta), …]
    deposits = []  # FIFO-Queue [(year, month, remaining_hours)]
    for y, m, delta in history:
        d = Decimal(str(delta))
        if d > 0:
            deposits.append([y, m, d])
        elif d < 0:
            owe = -d
            while owe > 0 and deposits:
                if deposits[0][2] <= owe:
                    owe -= deposits[0][2]; deposits.pop(0)
                else:
                    deposits[0][2] -= owe; owe = Decimal('0')
    if not deposits:
        return None
    oy, om, rem = deposits[0]
    age_months = (as_of.year - oy) * 12 + (as_of.month - om)
    return {"oldest_year": oy, "oldest_month": om, "age_months": age_months,
            "hours": float(rem), "overdue": age_months >= 12, "due_soon": 10 <= age_months < 12}
```

> `get_overtime_history` reale Signatur/Rückgabe in Task-Zeit prüfen (calculation_service.py:843) und die FIFO an das echte Format anpassen.

**Warncode:** `MILOG_SETTLEMENT_DUE: Konto-Stunden aus MM/YYYY (X.Xh) müssen bis MM/YYYY ausgeglichen werden (§2 Abs.2 MiLoG).` — `overdue` = deutlicher, `due_soon` = Hinweis.

**Surface:** Überstundenkonto + Monatsreport (NICHT am Stempel — Aging ist eine Monats-, keine Tagesfrage).

### 3.5 Warn-Kanal & UI

- Backend: bestehendes `warnings: list[str]`-Muster (wie ArbZG). Der Monatsreport-Response bekommt eine `milog_warnings`/`warnings`-Liste je MA (oder ein Flag im bestehenden Overview-Schema).
- Frontend: `utils/arbzgWarnings.ts` um `MILOG_ACCOUNT_50` + `MILOG_SETTLEMENT_DUE` erweitern (Detail-Text durchreichen). Inline-Badges im Überstundenkonto + Monatsreport.
- `UserForm`: Checkbox „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)" + Infozeile (aktueller Mindestlohn, abgeleitete vereinbarte Monatszeit, 50-%-Cap).
- `Settings.tsx`: Compliance-Karte „Gesetzlicher Mindestlohn" (aktuell + nächste Stufe).

### 3.6 DSGVO

Keine Lohn-/Verdienstdaten gespeichert (einfache Variante). Flag + Stunden sind bereits verarbeitete Beschäftigungsdaten. Keine neue sensible Kategorie. Das Flag ist admin-verwaltet; die Warnungen erscheinen für den MA (Eigenansicht) und Admins.

---

## 4. Außerhalb Scope

- **Baustein 2** (Wochen↔Monat-Umschaltung / Monatsmodus, echtes Monats-Soll) — eigener späterer Schritt.
- **603-€-Verdienstgrenze-Check** (Minijob-Grenze) — braucht Stundenlohn/Monatslohn → Lohndaten.
- Lohndaten-Speicherung.
- Automatischer Ausgleich (Auszahlung/Freizeit) — nur Warnung, kein Eingriff.

---

## 5. Teststrategie

**Backend:**
- `minimum_wage_for`: Grenzen (31.12.2025 → 12,82; 01.01.2026 → 13,90; 01.01.2027 → 14,60); `minimum_wage_info.next`.
- `agreed_monthly_hours`: 7,62 h/Woche → 33 h/Monat (± Rundung); respektiert `get_weekly_hours_for_date`.
- `milog_50_check`: unter/genau/über 50 %; Flag aus → None.
- `settlement_aging`: FIFO verbraucht ältesten Posten; überfällig ab 12 Monaten; kein offener Posten → None; Flag aus → None.
- `clock_out` emittiert `MILOG_ACCOUNT_50` nur bei Flag + Überschreitung; sonst nicht (bestehende clock_out-Tests bleiben grün).
- `/api/system/info` enthält `minimum_wage` (nie 500).
- Multi-Tenant: neue Spalte tenant-neutral (User ist tenant-scoped), F-026 unberührt.

**Frontend (Vitest):** `showArbzgWarnings` `MILOG_ACCOUNT_50`/`MILOG_SETTLEMENT_DUE`; `systemStore.minimumWage`; `UserForm` Checkbox + Infozeile.

**E2E (Playwright, API-driven, self-cleaning):** Flag-MA anlegen, Monat über 50 % füllen (TimeEntries), `clock_out`/Report liefert `MILOG_ACCOUNT_50`; Flag aus → keine Warnung.

---

## 6. Betroffene Dateien (Überblick)

**Backend:** `app/models/user.py` (+Flag) · `app/schemas/user.py` (Base/Update/Response) · `app/routers/admin_users.py` (create_user setzt Flag) · `alembic/versions/…` (Migration) · `app/core/minimum_wage.py` (neu) · `app/services/milog_service.py` (neu) · `main.py` (`system_info` → `minimum_wage`) · `app/routers/time_entries.py` (`clock_out`-Warnung) · `app/routers/admin_reports.py` bzw. Report-Service (Monats-Warnung) · `app/routers/*` Überstundenkonto-Endpoint.

**Frontend:** `src/stores/systemStore.ts` (minimum_wage) · `src/utils/arbzgWarnings.ts` (2 Codes) · `src/pages/admin/users/UserForm.tsx` (Checkbox+Info) · `src/types/user.ts` · `src/pages/admin/Settings.tsx` (Compliance-Karte) · Überstundenkonto-/Report-Komponente (Badges).

**Doku:** `docs/handbuch/HANDBUCH-ADMIN.md` + `DocViewer.tsx` (In-App-Hilfe) · `CLAUDE.md` (Regel).

---

## 7. Verbindliche Modellentscheidungen aus dem Härtungs-Review

Ein 8-Lens-Adversarial-Review (Verdict: tragfähig, kein Design-Change) hat die Rechen-/Rechtsmodellierung geprüft. Diese Entscheidungen **gelten** und überschreiben §§ 3.3/3.4:

1. **50-%-Basis = FLAT vereinbarte Monatszeit (nicht der Tages-Soll).** Beide Seiten des Vergleichs nutzen `agreed_monthly = weekly_hours × 13/3`:
   `account_hours = max(0, get_monthly_actual(y,m,up_to_date) − agreed_monthly)` gegen `cap = agreed_monthly / 2`.
   **Grund:** Der Tages-Soll (`get_monthly_target`) schwankt mit der Werktagszahl (20–23 Mo–Fr → ±~3 h ≈ 28 % des 16,5-h-Caps) **und** wird durch Abwesenheiten reduziert (ein bezahlter Urlaubstag würde sonst fälschlich Kapazität für Extra-Stunden freigeben). Die flache Monatszahl passt zum Minijob mit **festem Monatsentgelt/33 h** und neutralisiert beides. Der echte Monats-Soll kommt mit **Baustein 2**; bis dahin ist die Ableitung × 13/3 die Vertragsgröße. `milog_50_check` guardet zusätzlich auf `user.track_hours`.

2. **Warn-Wortlaut mit Mindestlohn-Caveat.** § 2 Abs. 2 bindet nur die **mindestlohnwirksamen** Stunden; da PraxisZeit keine Lohndaten hält, over-warnt eine reine Stundenprüfung bei Über-Mindestlohn-Vergütung. Alle 50-%-Warnungen + die UserForm-/Handbuch-Infozeile ergänzen: *„… sofern zur Mindestlohnhöhe vergütet; bei höherer Vergütung ggf. unkritisch — bitte prüfen."*

3. **FIFO-Aging seedet den Carryover.** `get_overtime_history_detailed` startet beim letzten `YearCarryover` und setzt den Saldo dort zurück → der **älteste** (überfällig-verdächtige) Bestand aus Vor-Carryover-Jahren fehlt. `settlement_aging` seedet den Carryover-Öffnungssaldo als ältesten Posten (gestempelt auf den Carryover-Monat); liegt trotzdem ein Reset im Aging-Fenster, kommt der Hinweis *„Konto kann nicht vollständig geprüft werden (älter als Abrechnungsfenster)"* statt eines stillen `None`.

4. **Überfällig-Semantik.** „binnen zwölf Kalendermonaten" → `overdue = age_months > 12`, `due_soon = 11 ≤ age ≤ 12`.

5. **MA-Eigenansicht als Warnfläche (Pflicht, war in §§ 3.3–3.6 genannt, aber im Plan nur admin-seitig).** Der MA sieht die Warnungen im **eigenen Überstundenkonto**: `GET /api/dashboard/overtime` (`OvertimeAccount`) trägt `milog_warnings` (self-scoped), Anzeige in `Dashboard.tsx`. **Push zusätzlich** an den MA-Selfservice-Schreibpfaden `create_time_entry` + `update_time_entry` (nicht nur `clock_out`) — der Ziel-MA bucht typischerweise **manuell**. `clock_in` bleibt ausgeschlossen (offener Eintrag, keine `net_hours`).

6. **`UserListResponse` trägt die neuen Felder.** Das Bearbeiten-Formular bezieht den User aus `GET /api/admin/users` → `List[UserListResponse]` (erbt **nicht** `UserBase`). `milog_working_time_account` **und** das bestehende `child_sick_days_per_year` (#376, latenter Bug) müssen dort ergänzt werden, sonst setzt jedes Speichern im Edit-Formular die Werte still auf Default zurück.

7. **`/admin/reports/monthly`:** bewusst **nicht** angefasst; die Admin-Warnfläche ist `users-overview` (Users.tsx). Deviation hier dokumentiert.
