"""Year-closing lock key (2026-11-02).

The F-029 advisory lock used ``hash((tenant, year)) & 0x7FFF…`` as the second
argument of ``pg_advisory_xact_lock(int, int)``. That value is a bigint, so
PostgreSQL rejected the call, the bare ``except`` swallowed the error and the
aborted transaction turned every year closing into an HTTP 500. ``hash()`` of a
string is also randomized per process, so two workers would never have shared
a key. The key must be deterministic and fit the one-argument bigint form.
"""
import subprocess
import sys

from app.routers.admin_carryovers import year_closing_lock_key

TENANT = "00000000-0000-0000-0000-000000000001"


def test_key_fits_a_signed_bigint():
    for year in (2000, 2025, 2100):
        key = year_closing_lock_key(TENANT, year)
        assert -(2**63) <= key < 2**63


def test_key_differs_per_year_and_tenant():
    keys = {year_closing_lock_key(TENANT, 2025), year_closing_lock_key(TENANT, 2026),
            year_closing_lock_key("00000000-0000-0000-0000-000000000002", 2025)}
    assert len(keys) == 3


def test_key_is_the_same_in_every_process():
    code = ("from app.routers.admin_carryovers import year_closing_lock_key;"
            f"print(year_closing_lock_key('{TENANT}', 2025))")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                           env={"PYTHONHASHSEED": seed, **_env()}).stdout.strip() for seed in ("1", "2")}
    assert outs == {str(year_closing_lock_key(TENANT, 2025))}


def _env():
    import os
    return {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
