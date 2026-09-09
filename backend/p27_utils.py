"""Utilitas bersama modul Fase 27 (Kas Bon, Aset Tetap, Pembiayaan, Marketing Fee).

Dipisah agar tidak ada duplikasi peta akun kas / aritmetika bulan di 4 modul.
"""
import calendar
import re
from datetime import datetime, timezone

from core_utils import WIB, now, now_iso, period_of  # noqa: F401 — CFG-01: period_of satu definisi

# Sumber/tujuan kas -> akun buku besar. SSOT grup `cash_source`.
CASH_ACCOUNT = {"kas": "1-1100", "bank": "1-1200"}
PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def cash_account(source: str) -> str:
    return CASH_ACCOUNT.get((source or "bank").lower(), "1-1200")


def rp(n) -> str:
    return f"Rp {int(n or 0):,}"


def parse_iso(value):
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def current_period() -> str:
    return now().astimezone(WIB).strftime("%Y-%m")


def validate_period(period: str) -> str:
    p = (period or "").strip()
    if not PERIOD_RE.match(p):
        raise ValueError("Periode harus berformat YYYY-MM (mis. 2026-08).")
    if p > current_period():
        raise ValueError(f"Periode {p} belum berjalan — penyusutan hanya boleh sampai "
                         f"periode {current_period()}.")
    return p


def period_end_iso(period: str) -> str:
    """Tanggal posting untuk sebuah periode: akhir bulan, atau hari ini bila bulan berjalan."""
    y, m = int(period[:4]), int(period[5:7])
    if period == current_period():
        return now_iso()
    last = calendar.monthrange(y, m)[1]
    return datetime(y, m, last, tzinfo=timezone.utc).isoformat()


def month_add(value, months: int) -> str:
    """Tambah `months` bulan ke tanggal ISO (hari dipangkas ke akhir bulan bila perlu)."""
    base = parse_iso(value) or now()
    total = base.month - 1 + int(months)
    y = base.year + total // 12
    m = total % 12 + 1
    d = min(base.day, calendar.monthrange(y, m)[1])
    return base.replace(year=y, month=m, day=d).isoformat()


def days_overdue(due_iso) -> int:
    due = parse_iso(due_iso)
    return (now() - due).days if due else 0
