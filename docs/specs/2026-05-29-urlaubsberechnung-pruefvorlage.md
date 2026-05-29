# Urlaubsberechnung in PraxisZeit — Sachverhaltsdarstellung zur fachlichen Prüfung

**Stand:** 29.05.2026
**Erstellt für:** Vorlage an Steuerberatung / arbeitsrechtliche Beratung (im Folgenden „Prüfer")
**Betrifft:** Methode der Urlaubsverrechnung in der Zeiterfassungs-Software PraxisZeit
**Interne Referenz:** Issue #156

> Dieses Dokument beschreibt **rein den Sachverhalt** — wie die Software Urlaub berechnet und welche Frage sich daraus ergibt. Es enthält **keine rechtliche Bewertung**; diese obliegt dem Prüfer. Die genannten Gesetzes-/Tarifbezüge dienen nur der Einordnung.

---

## 1. Worum geht es?

Die Praxis beschäftigt Mitarbeitende mit **sehr unterschiedlicher Tagesaufteilung** bei gleicher Wochenarbeitszeit-Logik, u. a.:

- **Mitarbeiterin A:** 20 Std./Woche, verteilt auf **5 Tage à 4 Std.**
- **Mitarbeiterin B:** 27 Std./Woche, verteilt auf **3 Tage à 9 Std.**

Es besteht die Sorge, dass die Software Urlaub **stundenbasiert/dezimal** verrechnet und dadurch Mitarbeitende mit kurzen Tagen gegenüber Mitarbeitenden mit langen Tagen **ungleich** behandelt. Zu klären ist, ob die aktuelle Berechnungsmethode zulässig ist oder auf eine **tagebasierte** Zählung (ganze/halbe Tage unabhängig von der Stundenzahl) umgestellt werden sollte.

Die Praxis ist **nicht tarifgebunden**; der MFA-Tarifvertrag rechnet Urlaub üblicherweise **in Tagen** ab, nicht dezimal in Stunden.

---

## 2. Wie die Software Urlaub aktuell berechnet (Mechanismus)

PraxisZeit führt das Urlaubskonto **intern in Stunden** und rechnet für die Anzeige in „Tage" um. Maßgeblich sind drei Größen:

1. **Tagessoll** (Stunden, die an einem Arbeitstag zu leisten sind)
   `Tagessoll = Wochenstunden ÷ Arbeitstage pro Woche`
   - A: 20 ÷ 5 = **4 Std./Tag**
   - B: 27 ÷ 3 = **9 Std./Tag**

2. **Urlaubsbudget** (Jahresanspruch)
   - In Tagen: ein konfigurierbarer Wert je Mitarbeiter:in. Die Software **schlägt** einen anteiligen Wert vor: `30 × Arbeitstage ÷ 5` (also 30 Tage bei 5-Tage-Woche, **18 Tage** bei 3-Tage-Woche). Dieser Vorschlag kann vom Administrator überschrieben werden.
   - Intern in Stunden: `Budget-Stunden = Budget-Tage × Tagessoll`.

3. **Verbrauch**
   - Jeder gebuchte Urlaubstag wird mit einer **Stundenzahl** gespeichert.
   - Die Anzeige „verbrauchte Tage" / „Resttage" entsteht durch Division:
     `verbrauchte Tage = verbrauchte Stunden ÷ Tagessoll` (Tagessoll **der jeweiligen Person**).

**Kernpunkt:** Der Umrechnungsteiler ist das **individuelle Tagessoll** der jeweiligen Person (4 Std. bzw. 9 Std.) — **nicht** ein fester 8-Stunden-Standardtag.

---

## 3. Konkrete Berechnungsergebnisse (in der Software gemessen)

Die folgenden Werte wurden direkt mit der Berechnungslogik der Software ermittelt (Jahresbudget anteilig: A = 30 Tage, B = 18 Tage):

| Buchung | Mitarbeiterin A (4 Std./Tag) | Mitarbeiterin B (9 Std./Tag) |
|---|---|---|
| **1 Urlaubstag, gebucht mit dem korrekten Tagessoll** (4 bzw. 9 Std.) | **1,0 Tag** abgezogen | **1,0 Tag** abgezogen |
| **1 ganze Urlaubswoche** (= alle Arbeitstage der Woche) | **5,0 Tage** (5 Arbeitstage) | **3,0 Tage** (3 Arbeitstage) |
| **1 Urlaubstag, gebucht mit dem Formular-Standardwert 8 Std.** | **2,0 Tage** abgezogen | **0,9 Tage** abgezogen |

**Interpretation:**

- **Solange ein Urlaubstag mit dem tatsächlichen Tagessoll der Person gebucht wird, ist die Verrechnung sachgerecht:** ein freier Arbeitstag kostet genau **einen** Urlaubstag, eine freie Woche kostet so viele Urlaubstage, wie die Person Arbeitstage hat. Bezogen auf den Jahresanspruch ist das anteilig gleich (A: 5 von 30 = ⅙ Woche; B: 3 von 18 = ⅙ Woche).
- **Verzerrung entsteht, wenn ein einzelner Tag mit einem abweichenden Stundenwert gebucht wird** — insbesondere mit dem **Formular-Standardwert von 8 Stunden**: Dann „kostet" ein freier Tag bei A **2,0** Urlaubstage und bei B **0,9** Urlaubstage. Dieser 8-Std.-Standard greift in der Einzeltag-Erfassung bei Mitarbeitenden, für die **kein individueller Tagesplan** hinterlegt ist (Mehrtages-/Wochenbuchungen verwenden dagegen automatisch das korrekte Tagessoll je Tag).

> **Hinweis zur Wahrnehmung:** Die in der Praxis genannten Werte „0,5 bzw. 1,125 Urlaubstage je freiem Tag" entsprechen einer Betrachtung **Tagesstunden ÷ 8** (4÷8 = 0,5; 9÷8 = 1,125). Die Software selbst teilt jedoch durch das **individuelle Tagessoll**, nicht durch 8. Die tatsächliche Verzerrung rührt daher nicht aus der Division durch 8, sondern aus dem **8-Std.-Standardwert beim Buchen eines Einzeltags**. Beide Phänomene führen zum selben Kernanliegen: die „Tage"-Verrechnung ist nicht in allen Konstellationen ein sauberer Ganz-/Halbtag.

---

## 4. Wo genau die Ungleichbehandlung entsteht

1. **Einzeltag-Buchung mit 8-Std.-Standard** (Hauptursache): siehe Tabelle oben. Betrifft Teilzeitkräfte ohne hinterlegten individuellen Tagesplan.
2. **Ungleichmäßige Tagesaufteilung:** Ist ein individueller Tagesplan hinterlegt (z. B. Mo 8 Std., Di–Fr je 3 Std.), wird ein Urlaubstag mit den **Stunden des konkreten Wochentags** gebucht, der Umrechnungsteiler bleibt aber das **Durchschnitts-Tagessoll**. Ein Montag-Urlaub kostet dann mehr als ein Dienstag-Urlaub.
3. **Nicht-anteiliges Budget:** Wird der vorgeschlagene anteilige Jahresanspruch (z. B. 18 Tage bei B) vom Administrator durch einen pauschalen Wert (z. B. 30) ersetzt, ist der **Vergleich der Resttage** zwischen Voll- und Teilzeit irreführend.

In Summe ist die „Tage"-Darstellung **nur dann durchgängig ein sauberer Ganz-/Halbtag**, wenn (a) mit dem korrekten Tagessoll gebucht wird, (b) keine ungleichmäßigen Tagespläne vorliegen und (c) das Budget anteilig gesetzt ist.

---

## 5. Rechtlicher Rahmen (nur zur Einordnung — Bewertung durch den Prüfer)

- **§ 3 Abs. 1 BUrlG** bemisst den Mindesturlaub in **Werktagen** (24 Werktage bei 6-Tage-Woche). Bei abweichender Verteilung der Arbeitstage wird der Anspruch nach ständiger BAG-Rechtsprechung **anteilig nach der Zahl der wöchentlichen Arbeitstage** umgerechnet — also tagebasiert, **unabhängig von der Stundenzahl je Tag**.
- **Übliche Praxis / MFA-Tarif:** Abrechnung in **ganzen bzw. halben Tagen**, unabhängig davon, wie viele Stunden an dem Tag gearbeitet würden.
- Eine **stundenbasierte/dezimale** Verrechnung kann sachgerecht sein, **solange sie im Ergebnis** zur tagebasierten Betrachtung passt (1 freier Arbeitstag = 1 Urlaubstag). Sie wird problematisch, sobald sie — wie unter Ziff. 3/4 gezeigt — von der reinen Tageszählung abweicht.

---

## 6. Fragen an den Prüfer

1. Ist die **tagebasierte Zählung** (1 freier Arbeitstag = 1 Urlaubstag, unabhängig von den Tagesstunden; Jahresanspruch anteilig nach Arbeitstagen) für unsere Konstellation die rechtlich gebotene Methode?
2. Ist eine **stundenbasierte/dezimale** Verrechnung zulässig, solange sie im Regelfall dasselbe Ergebnis liefert — und ist die unter Ziff. 3/4 beschriebene Abweichung (Einzeltag mit 8 Std., ungleiche Tagespläne) **rechtlich unkritisch oder zu beheben**?
3. Gibt es Vorgaben zur **Behandlung von Halbtagen** und zur **Rundung** (z. B. kaufmännisch, immer zugunsten der/des Beschäftigten)?
4. Wie ist mit **Bestandsdaten** umzugehen, falls die Methode umgestellt wird (rückwirkend vs. ab Stichtag)?

---

## 7. Mögliche Lösungswege in der Software (zur Information)

- **Sofortmaßnahme (geringer Aufwand):** Einzeltag-Buchungen verwenden künftig **immer das individuelle Tagessoll** statt des 8-Std.-Standards. Damit entspricht jeder volle freie Tag exakt 1 Urlaubstag (siehe Tabelle Ziff. 3, obere Zeile).
- **Option A — stundenbasiert (Status quo, korrigiert):** beibehalten, aber mit der Sofortmaßnahme; geeignet, wenn auch **stundenweise** Freistellungen sauber abgebildet werden sollen.
- **Option B — tagebasiert (konfigurierbar):** Urlaub wird ausschließlich in **ganzen/halben Tagen** geführt, unabhängig von den Tagesstunden — entspricht der üblichen MFA-Praxis. Größerer Umbau; als **pro-Praxis-Einstellung** umsetzbar, sodass beide Methoden wählbar sind.

Die Entscheidung zwischen A und B hängt von der rechtlichen Bewertung (Ziff. 6) ab.

---

## Anhang — Technische Fundstellen (für Rückfragen)

- Tagessoll: `backend/app/services/calculation_service.py → get_daily_target()` (`Wochenstunden ÷ Arbeitstage`).
- Urlaubskonto / Tage-Umrechnung: `get_vacation_account()` — `verbrauchte Tage = verbrauchte Stunden ÷ Tagessoll`, `Budget-Stunden = Budget-Tage × Tagessoll`.
- Anteiliger Budgetvorschlag: `backend/app/models/user.py → suggested_vacation_days` (`round(30 × Arbeitstage ÷ 5)`).
- 8-Std.-Standard bei Einzeltag-Erfassung: Frontend-Formular (`getHoursForDate` → 8 ohne individuellen Tagesplan); Mehrtagesbuchung verwendet `get_daily_target_for_date()` je Tag.

*Erstellt mit Unterstützung einer KI-gestützten Code-Analyse; die zugrundeliegenden Zahlen wurden direkt mit der Berechnungslogik der Software gemessen.*
