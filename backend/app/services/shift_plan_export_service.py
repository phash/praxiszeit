"""PDF-Aushang für einen Schichtplan (#443).

Bewusst ein eigenes Modul und **nicht** Teil von ``export_service``: dort liegt
die §16-/berechnungsgekoppelte Exportfläche, während die Schichtplanung (#305)
von der Berechnung entkoppelt ist. Ein eigenes Modul hält die Trennung sichtbar.

``generate_plan_pdf`` ist eine **reine** Funktion: sie bekommt das fertige Dict
von ``_build_plan_detail`` und hat keinen Datenbankzugriff. Damit kann das PDF
nicht zu einem zweiten Abfragepfad auswachsen, der dem Bildschirm davonläuft —
im Berechnungsmodell dieses Projekts ist genau das mehrfach passiert.

Aus ``export_service`` wird nur ``escape_pdf_text`` geliehen: eine reine
Textfunktion, kein Berechnungspfad.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.export_service import escape_pdf_text

WEEKDAY_LABELS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Marker vor einem Slot-Hinweis (»  statt ↳  — siehe Kommentar bei der Verwendung
# in _cell_paragraph). Als Konstante, damit test_shift_plan_pdf.py gezielt gegen
# genau dieses Zeichen prüfen kann, statt den kompletten Zellentext zu parsen.
NOTE_MARKER = "»"

_TITLE = ParagraphStyle("PlanTitle", fontName="Helvetica-Bold", fontSize=14, leading=17)
_META = ParagraphStyle("PlanMeta", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#4b5563"))
_HEAD = ParagraphStyle("PlanHead", fontName="Helvetica-Bold", fontSize=9, leading=11, alignment=TA_CENTER)
_CELL = ParagraphStyle("PlanCell", fontName="Helvetica", fontSize=8, leading=10)
_ROWHEAD = ParagraphStyle("PlanRowHead", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5)


def _fmt_date(iso: Optional[str]) -> str:
    """ISO-Datum → TT.MM.JJJJ. Unlesbare Eingaben werden unverändert
    durchgereicht statt eine Ausnahme zu werfen — ein Kopfzeilendetail darf
    keinen Ausdruck verhindern."""
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return str(iso)


def _validity_text(detail: dict) -> str:
    frm, until = _fmt_date(detail.get("active_from_date")), _fmt_date(detail.get("active_until_date"))
    if frm and until:
        return f"Gültig {frm} – {until}"
    if frm:
        return f"Gültig ab {frm}"
    if until:
        return f"Gültig bis {until}"
    return ""


def _cell_paragraph(slots_of_cell: list[dict]) -> Paragraph:
    """Eine Tabellenzelle: alle Einteilungen dieses Arbeitsplatzes an diesem Tag.

    Mehrere Einteilungen (z. B. Vormittag und Nachmittag) stapeln untereinander,
    getrennt durch eine Leerzeile.
    """
    if not slots_of_cell:
        return Paragraph("—", _CELL)
    blocks = []
    for s in sorted(slots_of_cell, key=lambda x: x.get("start_time") or ""):
        lines = [f"<b>{escape_pdf_text(s.get('start_time'))}–{escape_pdf_text(s.get('end_time'))}</b>"]
        names = [escape_pdf_text(a.get("user_name")) for a in (s.get("assignments") or [])]
        lines.append(", ".join(names) if names else "<i>nicht besetzt</i>")
        note = s.get("note")
        if note:
            # NOTE_MARKER (») statt Pfeil (↳): reportlab rendert mit der
            # Standardschrift Helvetica/WinAnsiEncoding — U+21B3 (↳) liegt dort
            # nicht, reportlab weicht dafür still auf ZapfDingbats mit einem
            # .notdef-artigen Ersatzglyph aus; im Ausdruck erscheint also ein
            # schwarzes Kästchen statt eines Pfeils. »  (U+00BB) liegt direkt in
            # WinAnsiEncoding und wird ohne Font-Wechsel korrekt dargestellt.
            # NICHT auf einen Pfeil zurückstellen — siehe test_shift_plan_pdf.py.
            lines.append(f"{NOTE_MARKER} {escape_pdf_text(note)}")
        blocks.append("<br/>".join(lines))
    return Paragraph("<br/><br/>".join(blocks), _CELL)


def generate_plan_pdf(
    detail: dict,
    *,
    weekdays: list,
    workstation_order: list,
    practice_name: Optional[str],
    generated_on: date,
) -> BytesIO:
    """Rendert einen Schichtplan als PDF-Aushang im Querformat A4.

    ``detail``            Das Dict von ``_build_plan_detail``.
    ``weekdays``          Freigeschaltete Planungstage (0=Mo … 6=So), #371 —
                          ein abgeschalteter Tag bekommt keine Spalte.
    ``workstation_order`` Arbeitsplatznamen in der gewünschten Zeilenreihenfolge.
                          Ein Name, der hier fehlt, wird hinten angehängt statt
                          verworfen.
    ``practice_name``     Praxisname für die Kopfzeile, optional.
    ``generated_on``      Das „Stand"-Datum. Wird hereingereicht statt intern
                          ermittelt, damit die Funktion rein und prüfbar bleibt.
    """
    days = sorted(d for d in weekdays if 0 <= d <= 6)
    if not days:
        days = [0, 1, 2, 3, 4]

    slots = [s for s in (detail.get("slots") or []) if s.get("weekday") in days]

    # Zeilen: erst die vorgegebene Reihenfolge, dann alles, was nur in den Slots
    # vorkommt (umbenannt, gelöscht, zwischenzeitlich verschoben).
    present = []
    for s in slots:
        nm = s.get("workstation_name") or "(ohne Arbeitsplatz)"
        if nm not in present:
            present.append(nm)
    rows_order = [n for n in workstation_order if n in present]
    rows_order += [n for n in present if n not in rows_order]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Schichtplan {detail.get('name') or ''}".strip(),
    )

    story = [Paragraph(escape_pdf_text(detail.get("name") or "Schichtplan"), _TITLE)]
    meta_bits = [b for b in (
        escape_pdf_text(practice_name) if practice_name else "",
        escape_pdf_text(detail.get("description") or ""),
        escape_pdf_text(_validity_text(detail)),
        f"Stand: {generated_on.strftime('%d.%m.%Y')}",
    ) if b]
    story.append(Paragraph(" · ".join(meta_bits), _META))
    story.append(Spacer(1, 5 * mm))

    header = [Paragraph("Arbeitsplatz", _HEAD)] + [Paragraph(WEEKDAY_LABELS[d], _HEAD) for d in days]
    table_data = [header]
    for ws_name in rows_order:
        row = [Paragraph(escape_pdf_text(ws_name), _ROWHEAD)]
        for d in days:
            row.append(_cell_paragraph([
                s for s in slots
                if (s.get("workstation_name") or "(ohne Arbeitsplatz)") == ws_name and s.get("weekday") == d
            ]))
        table_data.append(row)

    if len(table_data) == 1:
        # Kein einziger Slot auf einem freigeschalteten Tag. reportlab wirft bei
        # einer Tabelle ohne Datenzeile — stattdessen eine ehrliche Zeile.
        story.append(Paragraph("Für diesen Plan sind keine Einteilungen hinterlegt.", _CELL))
    else:
        usable = landscape(A4)[0] - 24 * mm
        first = 38 * mm
        col_widths = [first] + [(usable - first) / len(days)] * len(days)
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

    doc.build(story)
    buf.seek(0)
    return buf
