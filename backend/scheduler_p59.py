"""scheduler_p59.py — penjadwal Fase 59 (peninjauan tunggakan yang melewati batas SPR).

Mengikuti pola `scheduler_p45/p51`: mesinnya diimpor di dalam fungsi supaya `engine.py`
tetap di bawah batas 800 baris dan tidak ada impor melingkar.

Kenapa satu kali sehari dan kenapa hanya TUGAS: ambang tunggakan dihitung dalam BULAN, jadi
memeriksa lebih sering tidak menambah manfaat. Dan yang diterbitkan hanyalah tugas
peninjauan untuk Manajer Keuangan — penjadwal ini TIDAK PERNAH membatalkan kontrak.
Melepas rumah ke stok, membatalkan tagihan, dan menerbitkan utang refund adalah tiga
peristiwa uang yang harus punya nama manusia di belakangnya.
"""
import logging

logger = logging.getLogger("sipro.scheduler.p59")


async def arrears_review_tick() -> dict:
    import arrears_engine as arr
    out = await arr.sweep(actor="scheduler")
    if out.get("created"):
        logger.info("Tugas peninjauan tunggakan dibuat: %s", len(out["created"]))
    return out


def register(scheduler) -> list:
    jobs = [
        # 02:00 UTC = 09:00 WIB — tugas sudah ada di meja Manajer Keuangan saat jam kerja
        # dimulai, bukan tengah malam.
        (arrears_review_tick, {"trigger": "cron", "hour": 2, "minute": 0,
                               "id": "arrears_review_daily"}),
    ]
    for fn, kw in jobs:
        scheduler.add_job(fn, max_instances=1, coalesce=True, **kw)
    return [kw["id"] for _fn, kw in jobs]
