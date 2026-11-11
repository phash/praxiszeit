# Leitfaden: Handbücher und Cheat-Sheets erstellen

**Zweck:** Dieses Dokument beschreibt den Prozess und die Standards für die Erstellung und Aktualisierung der PraxisZeit-Nutzerdokumentation. Es ist intern und wird nie nach `frontend/public/help/` gespiegelt.

---

## Übersicht der Dokumentationsdateien

Die beiden **Handbücher** und **„So rechnet PraxisZeit“** sind das grafische Handbuch: Der Inhalt liegt als reine Daten in `frontend/src/handbuch/`, die Markdown-Dateien werden daraus **erzeugt** (nie von Hand bearbeiten, sie tragen oben den Hinweis „Erzeugt aus frontend/src/handbuch“). Cheat-Sheets und Schnellstart bleiben von Hand geschriebenes Markdown.

| Datei | Zielgruppe | Entsteht | Zweck |
|-------|-----------|----------|-------|
| `HANDBUCH-MITARBEITER.md` | Mitarbeitende | erzeugt | Handbuch mit Bildern, je Aufgabe eine Frage |
| `HANDBUCH-ADMIN.md` | Praxisleitung | erzeugt | Handbuch mit Bildern, je Aufgabe eine Frage |
| `SO-RECHNET-PRAXISZEIT.md` | alle | erzeugt | Soll, Ist, Saldo und Urlaub mit Rechenbeispielen |
| `CHEATSHEET-MITARBEITER.md` | Mitarbeitende | von Hand | Kompakte Kurzreferenz (1–2 Seiten) |
| `CHEATSHEET-ADMIN.md` | Praxisleitung | von Hand | Kompakte Kurzreferenz (1–2 Seiten) |
| `SCHNELLSTART.md` | Praxisleitung | von Hand | Von der Installation zur laufenden Zeiterfassung |

**Pfade:**
- Inhalt (Quelle der Handbücher): `frontend/src/handbuch/content/` (`mitarbeitende.ts`, `praxisleitung.ts`, `so-rechnet.ts`, `rechenbeispiele.json`), Aufnahmedefinitionen als `shots` im jeweiligen Inhalt
- Bilder: `frontend/public/help/img/*.webp` (aufgenommen), `frontend/src/handbuch/manifest.json` (Maße und Markierungsboxen je Bild)
- Erzeugte Markdown-Dateien: `docs/handbuch/*.md` (Bildlinks `img/…`, Kopie unter `docs/handbuch/img/`) und `frontend/public/help/*.md` (Download-Kopie, Bildlinks `/help/img/…`)
- Von Hand: `CHEATSHEET-*.md`, `SCHNELLSTART.md` in `docs/handbuch/` und byte-identisch in `frontend/public/help/`
- PDF-Dateien: keine im Repo — bei Bedarf erzeugen (siehe [Schritt 6](#6-pdf-dateien-bei-bedarf-erzeugen))

---

## Wann muss die Dokumentation aktualisiert werden?

- **UI-Änderungen:** Neue Seiten, geänderte Button-Bezeichnungen, neue Features, verschobene Navigationspunkte → Inhalt anpassen **und die betroffenen Bilder neu aufnehmen**
- **Feature-Entfernung:** Veraltete Aufgaben und Bilder löschen
- **Neue ArbZG-Prüfungen:** Gesetzliche Änderungen, neue Compliance-Reports
- **Formularänderungen:** Neue oder entfernte Pflichtfelder
- **Versionswechsel:** Der Kopf der erzeugten Handbücher nennt `**Stand:** PraxisZeit <Version>` aus `frontend/package.json`; nach dem Versionssprung `npm run handbuch:md` ausführen

---

## Prozess zur Aktualisierung

### 1. Neuen Branch erstellen

```bash
git checkout -b docs/handbuch-update-YYYY-MM-DD
```

### 2. Inhalt ändern

Texte und Schritte stehen in `frontend/src/handbuch/content/*.ts`; Typen und Regeln in `frontend/src/handbuch/types.ts` und `validate.ts`.

**Schreibstil:**
- Klare, präzise Sprache, **Sie-Form**, Begriffe laut `docs/GLOSSAR.md` („Arbeitszeit-Block“ = Vertrag, „Zeiteintrag“ = Stempel, „Mitarbeitende ohne Stundenzählung“)
- UI-Beschriftungen wortgleich zur App
- Jede Aufgabe beginnt mit einer Frage („Wie trage ich …?“) und nennt nummerierte Schritte
- Der Inhalt erfindet nichts: jede fachliche Aussage stammt aus der Doku (`docs/BERECHNUNGEN.md`, Glossar) oder dem App-Verhalten
- Gesetzeslinks als Markdown-Links, Berechnungen mit Link nach `docs/BERECHNUNGEN.md`
- Veraltete Begriffe stehen in `frontend/src/handbuch/content/forbiddenTerms.ts` und dürfen im Inhalt nicht vorkommen (`content.test.ts`)

Jedes Bild ist ein **Shot** (Persona, Seite, Markierungen mit Locator und Nummer, Alt-Text mit mindestens 40 Zeichen). Jede Markierungsnummer im Bild hat genau einen Schritt mit derselben Nummer und umgekehrt (`validate.ts`).

### 3. Bilder aufnehmen

Screenshots entstehen **nur** aus der Wegwerf-Instanz (Compose-Projekt `pzhandbuch`, Port 8099, Fantasie-Demodaten „Praxis am Lindenplatz“), nie aus der Dev-Datenbank:

```bash
bash e2e/handbuch/run.sh all        # Instanz bauen, Demodaten einspielen, Serveruhr auf den Stichtag stellen
cd e2e && npx tsx handbuch/capture.ts              # alle Shots
cd e2e && npx tsx handbuch/capture.ts --only <shotId,…>   # nur einzelne
bash e2e/handbuch/run.sh down       # Instanz samt Volumes entfernen
```

- Ein Locator muss beim Aufnehmen genau **ein sichtbares** Element treffen, sonst bricht die Aufnahme ab (geschrieben wird erst, wenn alle Shots gelungen sind).
- Aufnahmen: Desktop 1440×900 und mobil 390×844, zweifache Pixeldichte, WebP.
- **Kontaktseite ansehen:** `capture.ts` schreibt `e2e/handbuch/contact-sheet.html` und `contact-sheet.png` (lokal, gitignored): jedes Bild im Ausschnitt mit seinen Markierungen. Vor dem Commit durchsehen: schneiden Markierungsrahmen Beschriftungen ab, stimmen Nummern, ist kein Name oder Konto aus der echten Praxis zu sehen.
- Nach der Aufnahme sind `frontend/public/help/img/*.webp` und `frontend/src/handbuch/manifest.json` neu; beides committen. `capture.ts` nimmt alle gewählten Bilder neu auf (git meldet danach meist mehr geänderte Bilder, als inhaltlich neu sind) — unveränderte per `git restore` verwerfen, nachdem die gewollten mit `git add` vorgemerkt sind.

Die Demodaten bringt `backend/create_handbuch_testdata.py` mit (Admin „Dr. Andrea Werner“, Benutzer `admin`). Die Instanz ist wegwerfbar; das Passwort steht in `e2e/handbuch/capture.ts`.

- **Den Seed nie gegen eine echte Instanz laufen lassen:** er löscht die Konten `maria`, `thomas`, `sarah`, `petra`, `julia`, benennt den Admin um und setzt dessen Passwort auf einen öffentlichen Wert. Er bricht deshalb ohne `HANDBUCH_SEED=1` ab; nur `run.sh seed` und die PostgreSQL-Tests setzen es. Das Release-Paket für Kunden (Docker-Bundle) enthält die Datei nicht.
- **Ein zweites `seed` auf derselben Instanz scheitert** an einem Fremdschlüssel im Änderungsprotokoll: vorher `run.sh down`, dann `up` und `seed` (oder `all`).
- **Reihenfolge der Aufnahme:** Shots, die das Änderungsprotokoll zeigen (`/admin/audit-log`), laufen zuerst (`frontend/src/handbuch/shotOrder.ts`); sonst hinge ihr Bild davon ab, welche Shots mit Einstellungsänderung vorher liefen. Ein `--only`-Lauf und der volle Lauf liefern so dieselben Protokollbilder.

### 4. Markdown erzeugen

```bash
cd frontend && npm run handbuch:md
```

schreibt `docs/handbuch/HANDBUCH-MITARBEITER.md`, `HANDBUCH-ADMIN.md`, `SO-RECHNET-PRAXISZEIT.md`, die Download-Kopien in `frontend/public/help/` und die Bilder nach `docs/handbuch/img/` (nicht mehr gebrauchte Bilder dort werden entfernt). `npm run handbuch:md -- --check` vergleicht nur und endet mit Exit 1, wenn etwas abweicht — das tut auch die Gruppe `handbuch_md` des Doku-Abgleichs.

### 5. Von Hand gepflegte Dateien synchronisieren

Cheat-Sheets und Schnellstart nach jeder Änderung nach `frontend/public/help/` kopieren (Gruppe `mirror` prüft Byte-Gleichheit):

```bash
cp docs/handbuch/CHEATSHEET-MITARBEITER.md frontend/public/help/CHEATSHEET-MITARBEITER.md
cp docs/handbuch/CHEATSHEET-ADMIN.md frontend/public/help/CHEATSHEET-ADMIN.md
cp docs/handbuch/SCHNELLSTART.md frontend/public/help/SCHNELLSTART.md
```

Die In-App-Kurzanleitungen (`CheatsheetMitarbeiter`, `CheatsheetAdmin`) und der `SchnellstartAdmin` in `frontend/src/components/DocViewer.tsx` sowie die Kontexthilfe `frontend/src/constants/helpContent.tsx` pflegen Sie bei Änderungen mit. Das Handbuch selbst zeigt die App unter `/help` direkt aus dem Inhalt (`frontend/src/pages/Help.tsx`, `HandbookPage`); die Kontexthilfe verlinkt in die Kapitel.

**Fünf weitere Flächen**, die bei Handbuchänderungen mitgezogen werden: `docs/BERECHNUNGEN.md` + `docs/GLOSSAR.md`, die pzweb-Kopie (Anleitungsseiten im Webshop-Repo; Abgleich per `scripts/sync-handbuch-to-pzweb.sh`), die Kontexthilfe, die Kurzanleitungen und der Schnellstart.

Danach den gesamten Abgleich laufen lassen:

```bash
bash scripts/check-doc-sync.sh all
```

### 6. PDF-Dateien bei Bedarf erzeugen

Im Repo liegen bewusst **keine** PDF-Abzüge der Handbücher (auch nicht unter `frontend/public/`). Ein PDF neben der Markdown-Quelle veraltet mit der nächsten Änderung unbemerkt. `bash scripts/check-doc-sync.sh pdf` schlägt fehl, sobald wieder ein solches PDF eingecheckt wird.

Wer ein PDF braucht (z. B. zum Versenden), erzeugt es aus dem aktuellen Markdown-Stand und legt es außerhalb des Repos ab:

```bash
pandoc docs/handbuch/HANDBUCH-MITARBEITER.md \
  -o /tmp/Mitarbeiter-Handbuch.pdf \
  --pdf-engine=wkhtmltopdf \
  --metadata title="PraxisZeit – Mitarbeiter-Handbuch"
```

In der App laden Nutzer die Handbücher als Markdown aus `frontend/public/help/` herunter.

### 7. Committen und pushen

```bash
git add frontend/src/handbuch/ frontend/public/help/ docs/handbuch/ frontend/src/components/DocViewer.tsx
git commit -m "docs: Handbuch aktualisieren (vX.Y)"
git push origin docs/handbuch-update-YYYY-MM-DD
```

Dann Pull Request erstellen für Review.

---

## Inhaltliche Standards

### Was gehört ins Handbuch?

- Je Funktion eine Aufgabe mit Frage, Schritten und — wo es hilft — einem Bild mit nummerierten Markierungen
- Erklärungen aller Felder und Optionen, die man zum Ausführen der Aufgabe braucht
- Rechtliche Hintergründe (ArbZG-Paragraphen) mit Links
- FAQ-Abschnitt
- Hinweise („Achtung“, „Gut zu wissen“) für Stolperstellen

### Was gehört ins Cheat-Sheet?

- Nur die häufigsten / wichtigsten Aktionen
- Keine Erklärungen, nur Kurzanweisungen
- Tabellen für schnellen Überblick (Felder, Status, Limits)
- Gesetzliche Limits in Tabellenform
- Kontaktblock zum Ausfüllen (für Ausdruck)
- Maximal 2 DIN-A4-Seiten

---

## Qualitätssicherung

Vor dem Commit prüfen:

- [ ] `cd frontend && npx vitest run --pool=threads --maxWorkers=2` grün (`content.test.ts` prüft Verbotswörter, Markierung ↔ Schritt, Alt-Texte)
- [ ] Kontaktseite durchgesehen, keine echten Namen, keine abgeschnittenen Beschriftungen
- [ ] `npm run handbuch:md` ausgeführt, Ergebnis committet
- [ ] `bash scripts/check-doc-sync.sh all` grün
- [ ] Alle URLs und Navigationspfade stimmen mit der aktuellen App überein, Button-Bezeichnungen wortgleich
- [ ] Cheat-Sheets/Schnellstart nach `frontend/public/help/` kopiert
- [ ] Gesetzeslinks funktionieren

---

*Zuletzt aktualisiert: November 2026 (grafisches Handbuch)*
