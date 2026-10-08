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
Praxis auf einem Ausdruck?" für jede Fläche, die bisher ``Tenant.name`` dafür
nahm. Bewusst ein Ersatz zur Laufzeit statt einer Migration oder eines
Startup-Abgleichs:

* Die Konfiguration bleibt on-prem die Quelle. Wer ``PRACTICE_NAME`` später
  korrigiert (Docker-Installationen starten oft mit dem Vorgabewert
  „Praxis"), sieht den neuen Namen nach dem Neustart — eine einmalige Kopie in
  die Datenbank hätte den Wert des ersten Starts eingefroren.
* Die ``tenants``-Zeile bleibt unangetastet, insbesondere ``slug == "default"``
  — daran findet der Bootstrap den Mandanten wieder (#435).
* Ersetzt wird ausschließlich der Bootstrap-Platzhalter. Jeder andere Wert
  (SaaS-Signup-Name, der Anonymisierungs-Ersatz „[gelöscht]", ein künftig
  bewusst gesetzter Name) wird unverändert ausgegeben.
"""

from typing import Optional

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
