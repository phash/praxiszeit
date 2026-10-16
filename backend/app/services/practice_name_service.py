"""Praxisname für Ausdrucke und Kopfzeilen (#495).

On-prem legen Migration ``027`` (Bestandsinstallationen) und der Bootstrap in
``main.py`` (Neuinstallationen) den einzigen Mandanten mit ``name="Default"``
und ``slug="default"`` an. Der beim Installieren abgefragte Praxisname steht
dagegen in ``settings.PRACTICE_NAME`` (``[practice] name`` in
``config/praxiszeit.conf`` bzw. ``PRACTICE_NAME`` in der Docker-``.env``), und
on-prem gibt es keine Oberfläche, die ``Tenant.name`` ändert. Wer
``Tenant.name`` direkt als Praxisnamen druckt, zeigt dort also „Default" —
so geschehen im Schichtplan-Aushang.

``practice_display_name`` ist deshalb die EINE Antwort auf „wie heißt die
Praxis auf einem Ausdruck?" — genutzt vom Schichtplan-Aushang, vom AVV-Entwurf
und vom klassischen Jahresbericht (Zelle A1; der las bis dahin direkt
``settings.PRACTICE_NAME`` und zeigte in SaaS damit für jeden Mandanten den
Betreiber-Wert). Eine neue Fläche mit Praxisnamen ruft ebenfalls diesen
Helfer, weder ``Tenant.name`` noch ``PRACTICE_NAME`` direkt. Bewusst ein
Ersatz zur Laufzeit statt einer Migration oder eines Startup-Abgleichs:

* Die Konfiguration bleibt on-prem die Quelle. Wer ``PRACTICE_NAME`` später
  korrigiert (Docker-Installationen starten oft mit dem Vorgabewert
  „Praxis"), sieht den neuen Namen nach dem Neustart — eine einmalige Kopie in
  die Datenbank hätte den Wert des ersten Starts eingefroren.
* Die ``tenants``-Zeile bleibt unangetastet, insbesondere ``slug == "default"``
  — daran findet der Bootstrap den Mandanten wieder (#435).
* Ersetzt wird ausschließlich der Bootstrap-Platzhalter. Jeder andere Wert
  (SaaS-Signup-Name, der Anonymisierungs-Ersatz „[gelöscht]", ein künftig
  bewusst gesetzter Name) wird unverändert ausgegeben.

``practice_display_address`` ist dasselbe für die Anschrift (klassischer
Jahresbericht, Zelle B1): Bootstrap-Mandant → ``PRACTICE_ADDRESS`` aus der
Konfiguration, sonst die Abrechnungsanschrift des Mandanten — in SaaS NIE
``PRACTICE_ADDRESS``, das ist dort die Anschrift des Betreibers, nicht die der
Praxis.
"""

from typing import List, Optional

from app.config import settings
from app.core.deployment import is_onprem

# Was Migration 027 und der On-Prem-Bootstrap in ``main.py`` in die
# ``tenants``-Zeile schreiben. ``main.py`` liest den Namen von hier, damit
# Platzhalter und Erkennung nicht auseinanderlaufen; Migration 027 ist
# eingefroren und wird über einen Test gegen diese Werte gehalten.
DEFAULT_TENANT_NAME = "Default"
DEFAULT_TENANT_SLUG = "default"


def is_bootstrap_placeholder(tenant) -> bool:
    """True, wenn ``tenant`` on-prem noch den Bootstrap-Namen trägt."""
    return (
        tenant is not None
        and is_onprem()
        and tenant.slug == DEFAULT_TENANT_SLUG
        and (tenant.name or "").strip() == DEFAULT_TENANT_NAME
    )


def practice_display_name(tenant) -> Optional[str]:
    """Der Praxisname, wie er auf Ausdrucken und in Kopfzeilen stehen soll.

    On-prem mit unverändertem Bootstrap-Mandanten: der konfigurierte
    ``PRACTICE_NAME``. Sonst: ``tenant.name``. Ein leerer Wert ergibt ``None``
    — Aufrufer lassen den Namen dann weg, statt einen Platzhalter zu drucken.
    """
    if tenant is None:
        return None
    if is_bootstrap_placeholder(tenant):
        return (settings.PRACTICE_NAME or "").strip() or None
    return (tenant.name or "").strip() or None


def billing_address_parts(tenant) -> List[str]:
    """Straße und „PLZ Ort" aus den Abrechnungsdaten des Mandanten, als Rohtext.

    Die EINE Stelle, die ``tenants.billing_address`` (JSON, Form laut
    ``schemas.tenant.BillingAddress``) liest — genutzt von
    ``practice_display_address`` und vom AVV-Entwurf. Leere oder fehlende
    Teile entfallen; ein ``None`` aus dem Schema wird nie als „None" gedruckt.
    Das Land steht bewusst nicht darin (``tenant.country`` ist ein ISO-Code für
    die Steuerlogik; wer es drucken will, hängt es selbst an). Escaping ist
    Sache des Aufrufers (PDF: ``escape_pdf_text``, Tabelle:
    ``neutralize_spreadsheet_formula``).
    """
    addr = getattr(tenant, "billing_address", None)
    if not isinstance(addr, dict):
        return []

    def _part(key: str) -> str:
        return str(addr.get(key) or "").strip()

    street = _part("street")
    zip_city = f"{_part('zip')} {_part('city')}".strip()
    return [p for p in (street, zip_city) if p]


def practice_display_address(tenant) -> Optional[str]:
    """Die Praxisanschrift, wie sie auf Ausdrucken stehen soll (eine Zeile).

    On-prem mit unverändertem Bootstrap-Mandanten: das konfigurierte
    ``PRACTICE_ADDRESS`` (``[practice] address`` bzw. ``.env``). Sonst: die
    Abrechnungsanschrift des Mandanten („Straße, PLZ Ort"). Ohne Anschrift
    ``None`` — der Aufrufer lässt die Zelle dann leer, statt (in SaaS) die
    Anschrift des Betreibers unter den Namen einer fremden Praxis zu setzen.
    """
    if tenant is None:
        return None
    if is_bootstrap_placeholder(tenant):
        return (settings.PRACTICE_ADDRESS or "").strip() or None
    return ", ".join(billing_address_parts(tenant)) or None
