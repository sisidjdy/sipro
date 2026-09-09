"""scheduler_p45.py — job berkala Fase 45 (target dinamis & peringatan anggaran).

Dipisah dari `engine.py` karena berkas itu sudah menyentuh batas NFR 800 baris (gate
`validate_compliance`). Keduanya dibungkus di sini sebagai fungsi kecil yang MENGIMPOR
modulnya secara lokal, supaya scheduler tidak menarik seluruh lapisan anggaran/target saat
`engine` dimuat (menghindari impor melingkar: `budget_reports` → `engine`).
"""
import logging

logger = logging.getLogger("sipro.scheduler.p45")


async def targets_recalc_tick() -> int:
    """Penyesuaian target bulanan (`docs/v2/32` §2.1).

    Idempoten per bulan (`recalc_period`): menjalankan tick berulang TIDAK menumpuk jejak
    palsu di `history[]`. Periode lampau dikunci, jadi laporan historis tidak berubah.
    """
    import target_store as tstore
    return await tstore.recalc_tick()


async def budget_alert_tick() -> int:
    """Peringatan anggaran (≥ `budget.alert_pct`) → notifikasi in-app + tugas FN-11.

    Hanya mengirim saat TINGKAT status naik (aman → waspada → overbudget), supaya pemakai
    tidak menerima pesan yang sama tiap hari lalu mematikan notifikasi.
    """
    import budget_reports as br
    return await br.alert_tick()


def register(scheduler) -> list:
    """Daftarkan job berkala Fase 45 + 46 pada scheduler `engine`.

    Dipusatkan di sini karena `engine.py` sudah menyentuh batas NFR 800 baris — menambah
    job baru di sana berarti menabrak gate `validate_compliance`. Semua jadwal ditulis
    dalam UTC; komentar menyebut jam WIB agar keputusannya bisa ditinjau manusia.
    """
    from scheduler_p46 import permit_expiry_tick
    jobs = [
        # target: dicek tiap 6 jam, tetapi hanya MENULIS sekali per bulan per target
        (targets_recalc_tick, {"trigger": "interval", "seconds": 21600,
                               "id": "targets_recalc"}),
        # ambang anggaran 01:00 UTC (08:00 WIB) → tugas FN-11 sudah ada sebelum jam kerja
        (budget_alert_tick, {"trigger": "cron", "hour": 1, "minute": 0,
                             "id": "budget_alert"}),
        # kedaluwarsa izin 02:00 UTC (09:00 WIB) → perpanjangan izin butuh waktu kantor
        (permit_expiry_tick, {"trigger": "cron", "hour": 2, "minute": 0,
                              "id": "permit_expiry"}),
    ]
    for fn, kw in jobs:
        scheduler.add_job(fn, max_instances=1, coalesce=True, **kw)
    return [kw["id"] for _fn, kw in jobs]
