# Use-Case-Verzeichnis (UC-Inventar)

[`index.html`](index.html) ist das **durchsuchbare Use-Case-Verzeichnis** von PraxisZeit
— alle aus dem Code inventarisierten Use-Cases (Akteur, Auslöser, Hauptablauf,
beteiligte Endpoints/Frontend-Seiten, relevante ArbZG-/BUrlG-/DSGVO-Regeln) plus
ihr **Doku-Status** (dokumentiert / nicht) und **Implementierungs-Status**
(korrekt / Abweichung). Oben listet die Seite die offenen Findings (≥ medium).

Im Browser öffnen (Datei genügt, kein Server nötig):

```
xdg-open docs/uc/index.html      # Linux
open docs/uc/index.html          # macOS
```

Filter: Volltextsuche (ID/Titel/Endpoint/Ablauf), Akteur, Bereich, „nur
undokumentierte", „nur Impl.-Abweichungen". Karten zum Aufklappen anklicken.

## Pflege

Die Seite wird aus dem Ergebnis des UC-Review-Workflows generiert (ein JSON mit
`result.ucs[]` + `result.findings*`):

```
python3 docs/uc/_generate.py <uc-review.json>   # schreibt index.html neben das Skript
```

Bei größeren Funktionsänderungen den UC-Review erneut laufen lassen und neu
generieren, damit das Inventar aktuell bleibt. Quelle der Wahrheit für das
Verhalten bleibt der Code + `CLAUDE.md`/[`../GLOSSAR.md`](../GLOSSAR.md); dieses
Verzeichnis ist die navigierbare Übersicht.
