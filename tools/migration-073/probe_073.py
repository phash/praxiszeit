"""Spec 2026-10-08, Erfolgskriterium 4 / 17.1: Byte-Identität über Migration 073.

Schreibt je Person (sortiertes JSON nach stdout): ``net_hours`` je Eintrag,
Tagessoll je Kalendertag, Monats-Soll/-Ist je Monat und den Überstundensaldo —
vom ersten Eintrag bis heute. Läuft einmal mit dem Code VOR PR1 (.git/pr1-base) gegen
die Prod-Kopie auf 072 und einmal mit dem PR1-Code gegen dieselbe Kopie auf
073; ``diff`` der beiden Ausgaben muss leer sein.

Nutzt nur Funktionen, die es in 1.19.3 und nach PR1 gleichlautend gibt.
Aufruf im Backend-Image, Arbeitsverzeichnis = Backend der jeweiligen Version:
    python /probe/probe_073.py > /out/<name>.json

``PROBE_TODAY`` (ISO-Datum, optional) hält „heute" für alle Läufe eines Vergleichs
fest — sonst verschiebt ein Lauf über Mitternacht (Europe/Berlin) das Ende des
Zeitraums, und der Vergleich meldet eine Abweichung, die keine ist.
"""
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")

from app.database import SessionLocal, set_superadmin_context  # noqa: E402
from app.models import TimeEntry, User  # noqa: E402
from app.services import calculation_service as cs  # noqa: E402
from app.services.timezone_service import today_local  # noqa: E402


def _months(first: date, last: date):
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def main() -> None:
    db = SessionLocal()
    set_superadmin_context(db)
    today = date.fromisoformat(os.environ["PROBE_TODAY"]) if os.environ.get("PROBE_TODAY") else today_local()
    result = {}
    for user in db.query(User).filter(User.tenant_id.isnot(None)).order_by(User.id).all():
        entries = (
            db.query(TimeEntry)
            .filter(TimeEntry.user_id == user.id, TimeEntry.tenant_id == user.tenant_id)
            .order_by(TimeEntry.id)
            .all()
        )
        first = min((e.date for e in entries), default=today)
        daily, day = {}, first
        while day <= today:
            schedule = cs.get_schedule_for_date(db, user, day)
            daily[day.isoformat()] = str(cs.get_daily_target_for_date(user, day, schedule))
            day += timedelta(days=1)
        result[str(user.id)] = {
            "net_hours": {str(e.id): str(e.net_hours) for e in entries},
            "daily_target": daily,
            "months": {
                f"{y}-{m:02d}": [str(cs.get_monthly_target(db, user, y, m)),
                                 str(cs.get_monthly_actual(db, user, y, m))]
                for y, m in _months(first, today)
            },
            "overtime": str(cs.get_overtime_account(db, user, today.year, today.month)),
        }
    json.dump(result, sys.stdout, sort_keys=True, indent=1)
    db.close()


if __name__ == "__main__":
    main()
