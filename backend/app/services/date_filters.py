"""
F-033: Sargable date-range filters for hot reporting queries.

``WHERE extract('year', date) = 2026`` is not sargable — Postgres must run a
function on every row before comparing, so it cannot use a plain B-tree
index on the date column. Rewriting to ``WHERE date >= '2026-01-01' AND
date < '2027-01-01'`` is mechanically equivalent and fully index-friendly.

This module provides helpers that return a single SQLAlchemy ``and_()``
clause so the call-site rewrite is a one-line change:

    # Before:
    query.filter(
        extract("year", TimeEntry.date) == year,
        extract("month", TimeEntry.date) == month,
    )

    # After:
    query.filter(date_in_month(TimeEntry.date, year, month))
"""

from calendar import monthrange
from datetime import date
from sqlalchemy import and_


def date_in_year(column, year: int):
    """Range filter ``column IN year`` as a sargable BETWEEN-style expression."""
    return and_(
        column >= date(year, 1, 1),
        column < date(year + 1, 1, 1),
    )


def date_in_month(column, year: int, month: int):
    """Range filter ``column IN year-month`` as a sargable expression."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return and_(column >= start, column < end)


def date_in_year_up_to_month(column, year: int, month: int):
    """
    Range filter ``column IN year AND month <= :month`` as a sargable
    expression. Used by year-to-date export queries.
    """
    _, last_day = monthrange(year, month)
    return and_(
        column >= date(year, 1, 1),
        column <= date(year, month, last_day),
    )
