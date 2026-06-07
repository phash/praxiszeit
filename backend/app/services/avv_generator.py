"""AVV (Auftragsverarbeitungsvertrag §28 DSGVO) PDF generator
(Phase 6 / Issue #97).

This is intentionally a **scaffold** — the actual clause wording must be
signed off by a lawyer before anything is handed to a customer. The
generator fills in the tenant's practice details into a boilerplate
structure so an admin can download a personalised draft.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import TYPE_CHECKING

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.services.export_service import escape_pdf_text

if TYPE_CHECKING:
    from app.models.tenant import Tenant


_PROVIDER_NAME = "PraxisZeit (MR Development)"
_PROVIDER_ADDRESS = "Manuel Rödig · Lindenallee 1 · 61118 Bad Vilbel"


def generate_avv_pdf(tenant: "Tenant") -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"AVV – {tenant.name}")
    styles = getSampleStyleSheet()

    def p(text: str, style_name: str = "Normal"):
        return Paragraph(text, styles[style_name])

    now = datetime.now(timezone.utc).strftime("%d.%m.%Y")

    story = [
        p("Auftragsverarbeitungsvertrag (AVV) gemäß §28 DSGVO", "Title"),
        Spacer(1, 12),
        p(f"<b>Stand:</b> {now}"),
        p("<b>Status:</b> Entwurf – juristische Prüfung erforderlich."),
        Spacer(1, 12),

        p("<b>1. Parteien</b>", "Heading2"),
        p("<b>Auftragsverarbeiter</b>"),
        p(f"{_PROVIDER_NAME}"),
        p(_PROVIDER_ADDRESS),
        Spacer(1, 6),
        p("<b>Verantwortlicher</b>"),
        p(escape_pdf_text(tenant.company_name or tenant.name)),
        p(_address_line(tenant) or "<i>Keine Anschrift hinterlegt – bitte in den Abrechnungsdaten ergänzen.</i>"),
        p(f"USt-ID: {escape_pdf_text(tenant.vat_id) if tenant.vat_id else '—'}"),
        Spacer(1, 12),

        p("<b>2. Gegenstand und Dauer der Verarbeitung</b>", "Heading2"),
        p(
            "Der Auftragsverarbeiter stellt dem Verantwortlichen die Software "
            "<i>PraxisZeit</i> zur Arbeitszeiterfassung gemäß ArbZG bereit. Die "
            "Verarbeitung erfolgt für die Dauer des Nutzungsvertrages sowie für "
            "die in §16 ArbZG vorgeschriebene Aufbewahrungsfrist von 2 Jahren."
        ),
        Spacer(1, 12),

        p("<b>3. Art und Zweck der Datenverarbeitung</b>", "Heading2"),
        p(
            "Speicherung und Verarbeitung von Arbeitszeitdaten, Pausenzeiten, "
            "Urlaubs- und Krankheitsmeldungen sowie damit verbundenen Stammdaten "
            "der Mitarbeiter des Verantwortlichen. Zweck ist die gesetzeskonforme "
            "Arbeitszeitdokumentation nach ArbZG, EU-Arbeitszeit-RL und DSGVO."
        ),
        Spacer(1, 12),

        p("<b>4. Betroffene Personen und Datenkategorien</b>", "Heading2"),
        p(
            "Mitarbeiter des Verantwortlichen. Datenkategorien: Name, E-Mail, "
            "Rolle, Arbeitszeit, Pausen, Urlaub, Abwesenheitsart, optional "
            "Profilbild. Besondere Kategorien (Art. 9 DSGVO) wie "
            "Krankheitszeiten werden im Mitarbeiter-Kalender maskiert."
        ),
        Spacer(1, 12),

        p("<b>5. Technisch-organisatorische Maßnahmen (TOM)</b>", "Heading2"),
        p(
            "• TLS 1.2+ im Transit (Pflicht bei DEPLOYMENT_MODE=saas).<br/>"
            "• bcrypt-Hashes für Passwörter (Cost ≥ 12).<br/>"
            "• Postgres Row-Level-Security, Mandantentrennung per tenant_id.<br/>"
            "• Backups verschlüsselt, 30 Tage Aufbewahrung.<br/>"
            "• Zugangsrollen: Admin / Mitarbeiter / Superadmin. 2FA verfügbar."
        ),
        Spacer(1, 12),

        p("<b>6. Unterauftragsverarbeiter</b>", "Heading2"),
        p(
            "Aktuell: Hetzner Online GmbH (Hosting, EU), Stripe Inc. (Zahlung, "
            "EU-US DPF), optional SMTP-Dienstleister. Änderungen werden dem "
            "Verantwortlichen mit einer Frist von 4 Wochen mitgeteilt."
        ),
        Spacer(1, 12),

        p("<b>7. Rechte des Verantwortlichen</b>", "Heading2"),
        p(
            "Weisungsrecht, Kontrollrecht, Recht auf Auskunft, Berichtigung, "
            "Löschung und Datenportabilität gemäß Art. 15 ff. DSGVO."
        ),
        Spacer(1, 18),

        p("<i>Dieses Dokument ist ein automatisch generierter Entwurf und "
          "ersetzt keine juristische Beratung.</i>", "Italic"),
    ]

    doc.build(story)
    return buf.getvalue()


def _address_line(tenant: "Tenant") -> str | None:
    addr = tenant.billing_address or {}
    if not addr:
        return None
    # Escape each part individually so the intentional <br/> separators survive
    # while user-controlled address fields can't inject reportlab markup.
    street = escape_pdf_text(addr.get("street", ""))
    zip_ = escape_pdf_text(addr.get("zip", ""))
    city = escape_pdf_text(addr.get("city", ""))
    country = escape_pdf_text(tenant.country or "")
    parts = [p for p in (street, f"{zip_} {city}".strip(), country) if p and p.strip()]
    return "<br/>".join(parts) or None
