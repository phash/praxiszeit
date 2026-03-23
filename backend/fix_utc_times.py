"""
Fix UTC→CET time shift for clock-in/clock-out entries.

Problem: Between 2026-03-09 and 2026-03-23 ~07:55 CET, start_time/end_time
were stored in UTC instead of Europe/Berlin (CET = UTC+1).

Strategy:
- Only correct entries created BEFORE the fix was deployed (created_at < 2026-03-23 06:50 UTC)
- Exclude user 'MCS' (enters times manually — already correct)
- Add +1 hour to start_time and end_time (all dates within CET, before DST on 2026-03-29)
- Dry-run mode by default, pass --apply to actually write changes

Usage:
    docker-compose exec backend python fix_utc_times.py          # Dry run
    docker-compose exec backend python fix_utc_times.py --apply  # Apply changes
"""

import sys
from datetime import date, time, timedelta, datetime, timezone
from sqlalchemy import create_engine, text
from app.config import settings

CUTOFF_DATE = date(2026, 3, 9)
# Fix was deployed at ~07:55 CET = 06:55 UTC on 2026-03-23.
# Use 06:50 UTC as safe cutoff to exclude post-fix entries.
FIX_DEPLOYED_AT = datetime(2026, 3, 23, 6, 50, 0, tzinfo=timezone.utc)
EXCLUDE_USERNAME = "MCS"
OFFSET_HOURS = 1  # CET = UTC+1 (no DST in this period)


def add_hours_to_time(t: time, hours: int) -> time:
    """Add hours to a time value."""
    dt = datetime.combine(date.today(), t) + timedelta(hours=hours)
    return dt.time()


def main():
    apply = "--apply" in sys.argv
    mode = "APPLY" if apply else "DRY RUN"
    print(f"\n=== UTC→CET Time Fix ({mode}) ===\n")
    print(f"Scope: entries from {CUTOFF_DATE} created before {FIX_DEPLOYED_AT.isoformat()}")
    print(f"Excluding user: {EXCLUDE_USERNAME}\n")

    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        # Show affected entries
        rows = conn.execute(text("""
            SELECT te.id, u.username, u.first_name, u.last_name,
                   te.date, te.start_time, te.end_time, te.created_at
            FROM time_entries te
            JOIN users u ON u.id = te.user_id
            WHERE te.date >= :cutoff
              AND te.created_at < :fix_deployed
              AND u.username != :exclude
            ORDER BY te.date, u.last_name, te.start_time
        """), {"cutoff": CUTOFF_DATE, "fix_deployed": FIX_DEPLOYED_AT, "exclude": EXCLUDE_USERNAME}).fetchall()

        if not rows:
            print("No entries found to correct.")
            return

        print(f"Found {len(rows)} entries to correct (+{OFFSET_HOURS}h):\n")
        print(f"{'User':<25} {'Date':<12} {'Start':<8} {'-> New':<8} {'End':<8} {'-> New':<8}")
        print("-" * 85)

        for row in rows:
            name = f"{row[2]} {row[3]}"
            entry_date = row[4]
            old_start = row[5]
            old_end = row[6]

            new_start = add_hours_to_time(old_start, OFFSET_HOURS) if old_start else None
            new_end = add_hours_to_time(old_end, OFFSET_HOURS) if old_end else None

            end_str = str(old_end)[:5] if old_end else "open"
            new_end_str = str(new_end)[:5] if new_end else "open"

            print(f"{name:<25} {entry_date}  {str(old_start)[:5]}  -> {str(new_start)[:5]}  {end_str:<8}-> {new_end_str}")

        # Show excluded entries for reference
        excluded = conn.execute(text("""
            SELECT te.id, u.username, u.first_name, u.last_name,
                   te.date, te.start_time, te.end_time
            FROM time_entries te
            JOIN users u ON u.id = te.user_id
            WHERE te.date >= :cutoff
              AND te.created_at < :fix_deployed
              AND u.username = :exclude
            ORDER BY te.date, te.start_time
        """), {"cutoff": CUTOFF_DATE, "fix_deployed": FIX_DEPLOYED_AT, "exclude": EXCLUDE_USERNAME}).fetchall()

        if excluded:
            print(f"\n--- Excluded ({EXCLUDE_USERNAME}, manual entries, NOT corrected): ---")
            for row in excluded:
                name = f"{row[2]} {row[3]}"
                end_str = str(row[6])[:5] if row[6] else "open"
                print(f"  {name:<25} {row[4]}  {str(row[5])[:5]} - {end_str}")

        # Show post-fix entries that will NOT be touched
        post_fix = conn.execute(text("""
            SELECT te.id, u.first_name, u.last_name,
                   te.date, te.start_time, te.end_time
            FROM time_entries te
            JOIN users u ON u.id = te.user_id
            WHERE te.date >= :cutoff
              AND te.created_at >= :fix_deployed
            ORDER BY te.date, te.start_time
        """), {"cutoff": CUTOFF_DATE, "fix_deployed": FIX_DEPLOYED_AT}).fetchall()

        if post_fix:
            print(f"\n--- Post-fix entries (already correct, NOT touched): ---")
            for row in post_fix:
                name = f"{row[1]} {row[2]}"
                end_str = str(row[5])[:5] if row[5] else "open"
                print(f"  {name:<25} {row[3]}  {str(row[4])[:5]} - {end_str}")

        if not apply:
            print(f"\n>>> DRY RUN - no changes made. Run with --apply to commit changes.\n")
            return

        # Apply the correction
        result = conn.execute(text("""
            UPDATE time_entries
            SET start_time = start_time + interval '1 hours',
                end_time = CASE
                    WHEN end_time IS NOT NULL THEN end_time + interval '1 hours'
                    ELSE NULL
                END,
                updated_at = NOW()
            WHERE date >= :cutoff
              AND created_at < :fix_deployed
              AND user_id NOT IN (SELECT id FROM users WHERE username = :exclude)
        """), {"cutoff": CUTOFF_DATE, "fix_deployed": FIX_DEPLOYED_AT, "exclude": EXCLUDE_USERNAME})
        conn.commit()

        print(f"\n>>> APPLIED: {result.rowcount} entries corrected by +{OFFSET_HOURS}h.\n")


if __name__ == "__main__":
    main()
