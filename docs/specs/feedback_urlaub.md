Inhaltlich spricht sehr viel dafür, dass eure Analyse korrekt ist — und dass die aktuelle Implementierung in bestimmten Konstellationen arbeitsrechtlich angreifbar sein kann.

Die entscheidende juristische Leitlinie lautet:

> Urlaub wird im deutschen Urlaubsrecht grundsätzlich nach **Arbeitstagen**, nicht nach Arbeitsstunden bemessen.

Das zieht sich durch:

* § 3 BUrlG,
* BAG-Rechtsprechung,
* IHK/Haufe-Fachliteratur,
* und die übliche arbeitsrechtliche Praxis. ([Haufe.de News und Fachwissen][1])

---

# Juristische Kernaussage

## 1. Das „Tagesprinzip“ ist der zentrale Maßstab

Die Rechtsprechung betrachtet Urlaub primär als:

* Freistellung von der Arbeitspflicht an einem Arbeitstag,
* nicht als Stundenkontingent.

Haufe formuliert das sehr deutlich:

> „Das Urlaubsrecht geht vom Tagesprinzip aus.“ ([Haufe.de News und Fachwissen][2])

Ebenso:

* Für die Urlaubsdauer kommt es auf die Zahl der Arbeitstage an,
* nicht auf die Länge der täglichen Arbeitszeit. ([Haufe.de News und Fachwissen][1])

Das bestätigt exakt eure Grundannahme im PDF.

---

# 2. Eure anteilige Umrechnung nach Arbeitstagen ist korrekt

Die Berechnung:

[
30 \times \frac{\text{Arbeitstage}}{5}
]

entspricht der üblichen BAG-konformen Teilzeitumrechnung. ([Haufe.de News und Fachwissen][1])

Beispiele:

* 5 Tage/Woche → 30 Urlaubstage
* 3 Tage/Woche → 18 Urlaubstage

Das ist arbeitsrechtlich Standard.

Der relevante Punkt:
Nicht die Wochenstunden sind entscheidend,
sondern die Anzahl der Arbeitstage. ([Arbeitsrechte][3])

---

# 3. Eure „korrigierte Stundenlogik“ ist wahrscheinlich zulässig

Der wichtige Unterschied:

## Wahrscheinlich zulässig

Wenn intern zwar mit Stunden gerechnet wird, aber:

* jeder freie Arbeitstag exakt 1 Urlaubstag verbraucht,
* eine freie Woche proportional gleich behandelt wird,
* keine Benachteiligung entsteht,

dann dürfte das juristisch meist akzeptabel sein.

Das entspricht faktisch nur einer technischen Speicherform.

Genau das macht eure „Sofortmaßnahme“:

* individueller Tagessollwert statt 8h-Default.

Dadurch wird:

* 1 Arbeitstag Urlaub = 1 Urlaubstag Verbrauch.

Das ist der entscheidende Punkt.

---

# 4. Der 8-Stunden-Default ist das eigentliche Risiko

Das ist vermutlich eure stärkste juristische Erkenntnis.

Denn hier entsteht tatsächlich eine Ungleichbehandlung:

| Person   | Tatsächlicher Arbeitstag | Gebuchter Urlaub |
| -------- | ------------------------ | ---------------- |
| 4h-Kraft | 1 freier Tag             | 2 Urlaubstage    |
| 9h-Kraft | 1 freier Tag             | 0,9 Urlaubstage  |

Das widerspricht dem Tagesprinzip massiv.

Denn:

* derselbe freie Arbeitstag
* verbraucht unterschiedlich viel Urlaub.

Das dürfte sehr schwer zu rechtfertigen sein. ([Haufe.de News und Fachwissen][2])

---

# 5. Ungleichmäßige Tagespläne sind juristisch heikel

Das ist der schwierigste Punkt.

Beispiel:

* Montag 8h
* Dienstag 3h

Wenn:

* Montag mehr Urlaub „kostet“ als Dienstag,
* obwohl beides jeweils ein Arbeitstag ist,

kollidiert das mit dem klassischen Tagesprinzip.

Haufe beschreibt genau dieses Problem:

* bei ungleich verteilten Arbeitszeiten,
* unabhängig von den Stunden,
* bleibt grundsätzlich der Arbeitstag entscheidend. ([Haufe.de News und Fachwissen][2])

Das spricht eher gegen:

* unterschiedliche „Kosten“ einzelner Arbeitstage.

---

# 6. Halbe Urlaubstage

Das BUrlG kennt eigentlich nur Urlaubstage.

Halbe Tage sind:

* betriebliche Praxis,
* tarifliche oder arbeitsvertragliche Gestaltung,
* aber kein gesetzlicher Grundmechanismus.

Eure Frage dazu ist juristisch absolut berechtigt.

Wichtig:
Wenn halbe Tage zugelassen werden,
muss die Logik konsistent und diskriminierungsfrei sein.

---

# 7. Was ein Arbeitsrechtler wahrscheinlich empfehlen wird

Mit hoher Wahrscheinlichkeit etwa Folgendes:

## Empfehlung A (wahrscheinlich bevorzugt)

### Tagebasierte Führung

* Urlaub in Tagen
* optional halbe Tage
* unabhängig von Stunden pro Tag

Das ist:

* rechtlich am robustesten,
* am verständlichsten,
* BAG-nah,
* MFA-praxisnah.

---

## Empfehlung B (wahrscheinlich noch zulässig)

### Stundenbasiert intern — aber nur vollständig äquivalent

Also nur wenn:

* jeder freie Arbeitstag exakt 1 Urlaubstag kostet,
* keine Verzerrung durch Defaults entsteht,
* keine Benachteiligung bei Teilzeit,
* keine Unterschiede zwischen langen/kurzen Tagen.

Dann ist die Stundenführung wohl eher ein technisches Detail.

---

# 8. Meine fachliche Einschätzung zur Softwarearchitektur

## Sofortmaßnahme

Die solltet ihr wahrscheinlich unabhängig von der Rechtsprüfung umsetzen:

> Kein 8h-Default mehr bei Einzeltagen.

Denn:

* das ist technisch klar fehleranfällig,
* arbeitsrechtlich schwer verteidigbar,
* und erzeugt reale Verzerrungen.

---

# 9. Wahrscheinlich kritischster Satz für eine Prüfung

Der juristisch gefährlichste Befund ist:

> „Ein Montag-Urlaub kostet mehr als ein Dienstag-Urlaub.“

Denn genau das widerspricht sehr wahrscheinlich:

* dem Gleichbehandlungsgrundsatz,
* dem Tagesprinzip,
* und der üblichen BAG-Logik.

---

# 10. Zusammenfassende Bewertung wie ein Steuerberater/Prüfer

## Wahrscheinlich rechtlich unkritisch:

* anteilige Urlaubstage nach Arbeitstagen,
* interne Stundenführung,
* Durchschnitts-Tagessoll,
* sofern Ergebnis immer tageäquivalent bleibt.

## Wahrscheinlich problematisch:

* 8h-Standardwert,
* unterschiedliche Urlaubskosten einzelner Arbeitstage,
* jede Logik, bei der ein freier Arbeitstag nicht exakt „1 Urlaubstag“ entspricht.

---

# Mein fachliches Fazit

Eure Analyse ist:

* technisch sauber,
* arbeitsrechtlich gut durchdacht,
* und identifiziert wahrscheinlich korrekt die eigentliche Schwachstelle.

Der entscheidende Punkt ist nicht:

> „stundenbasiert vs tagebasiert“

sondern:

> Entsteht im Ergebnis eine vom Tagesprinzip abweichende Benachteiligung?

Und genau das scheint:

* beim 8h-Default
* und bei ungleichen Tagesplänen

tatsächlich der Fall zu sein.

[1]: https://www.haufe.de/personal/haufe-personal-office-platin/urlaub-berechnung-teilzeit-sonderfaelle-3-teilzeit_idesk_PI42323_HI2713475.html?utm_source=chatgpt.com "Urlaub: Sonderfälle / 1 Teilzeittätigkeit | Haufe"
[2]: https://www.haufe.de/id/beitrag/5-urlaub-ii-sonderfaelle-in-teilzeitverhaeltnissen-HI16702686.html?utm_source=chatgpt.com "§ 5 Urlaub / II. Sonderfälle in Teilzeitverhältnissen | Haufe"
[3]: https://www.arbeitsrechte.de/urlaubsanspruch-teilzeit/?utm_source=chatgpt.com "Urlaubsanspruch bei Teilzeit: Was Ihnen 2026 zusteht"
