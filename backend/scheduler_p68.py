"""scheduler_p68.py — denda keterlambatan terjadwal (Fase 68).

Mengikuti pola `scheduler_p51/p59`: mesin diimpor di dalam fungsi supaya `engine.py` tetap
ramping dan tidak ada impor melingkar.

Kenapa harian dan kenapa hanya MENAGIHKAN: denda dihitung prorata HARI, jadi sekali sehari
cukup; idempotensi per (termin, bulan) milik `late_fee_engine` membuat putaran ganda aman.
Yang tidak pernah dilakukan penjadwal: meringankan denda (milik Manajer Keuangan) dan
membatalkan kontrak (alur Fase 56/59). Menagih otomatis pun tetap OPSI per organisasi
(`payment.late.auto_apply`, bawaan MATI) — keputusan bisnis, bukan bawaan kode.
"""
import logging

logger = logging.getLogger("sipro.scheduler.p68")


async def late_fee_auto_tick() -> dict:
    import late_fee_auto as lfa
    from db import ORG_ID, db
    out = {}
    orgs = await db.orgs.distinct("id") or [ORG_ID]
    for org in orgs:
        try:
            conf = await lfa.config(org)
            if not conf["enabled"]:
                continue
            res = await lfa.run(org, actor="scheduler", mode="auto")
            if res.get("charged_count"):
                out[org] = res["detail"]
        except Exception:  # noqa: BLE001 — satu organisasi gagal jangan mematikan sisanya
            logger.exception("Denda otomatis gagal untuk org %s", org)
    if out:
        logger.info("Denda otomatis harian: %s", out)
    return out


def register(scheduler) -> list:
    jobs = [
        # 02:30 UTC = 09:30 WIB — SESUDAH pengingat WA (08:00) dan tugas peninjauan
        # tunggakan (09:00): pembeli diingatkan dulu, baru dendanya ditagihkan.
        (late_fee_auto_tick, {"trigger": "cron", "hour": 2, "minute": 30,
                              "id": "late_fee_auto_daily"}),
    ]
    for fn, kw in jobs:
        scheduler.add_job(fn, max_instances=1, coalesce=True, **kw)
    return [kw["id"] for _fn, kw in jobs]
