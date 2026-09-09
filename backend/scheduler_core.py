"""scheduler_core.py — pembungkus job berkala milik fase-fase INTI (27, 31, 32, 33, 44).

## Kenapa berkas ini ada

`engine.py` memegang tiga hal sekaligus: event bus, dispatcher, dan pendaftaran scheduler.
Berkas itu tumbuh mengikuti tiap fase baru sampai menyentuh batas NFR 800 baris (gate
`validate_compliance`) — dan Fase 51B menabraknya (802 baris). Pola yang SUDAH dipakai repo
ini sejak Fase 45 adalah memindahkan job berkala ke modul kecil (`scheduler_p45.py`,
`scheduler_p46.py`, `scheduler_p51.py`), bukan memangkas komentar sampai kodenya tidak bisa
dijelaskan lagi. Berkas ini menyelesaikan utang itu untuk job fase inti yang sebelumnya masih
menumpang di `engine.py`.

## Aturan yang dijaga di sini

1. **Impor mesinnya LOKAL (di dalam fungsi).** Semua modul di bawah ini (`finance_engine`,
   `loans`, `build_monitor`, `analytics_engine`, `build_reports`) pada akhirnya mengimpor
   `engine` untuk membuat tugas/notifikasi. Mengimpornya di puncak berkas akan melahirkan
   impor melingkar saat `engine` dimuat.
2. **Kegagalan satu job TIDAK mematikan scheduler.** Tiap pembungkus menangkap galat,
   menuliskannya ke log dengan jejak, lalu mengembalikan nilai kosong yang jujur (0 / dict
   kosong) — bukan berpura-pura berhasil.
3. **Tidak ada logika bisnis di sini.** Berkas ini hanya jembatan waktu → mesin; keputusannya
   tetap milik mesin masing-masing supaya bisa diuji tanpa scheduler.
"""
import logging

logger = logging.getLogger("sipro.scheduler.core")


async def finance_retention_tick() -> int:
    """Fase 33: retensi subkon yang masa pemeliharaannya lewat → siap diajukan pencairan."""
    from finance_engine import ap_retention_release_sweeper
    try:
        return await ap_retention_release_sweeper()
    except Exception:  # noqa: BLE001
        logger.exception("Sapuan retensi subkon gagal")
        return 0


async def p27_reminder_tick() -> int:
    """Fase 27: pengingat angsuran pembiayaan jatuh tempo + kas bon belum dipertanggungjawabkan."""
    import loans
    import petty_cash
    made = 0
    try:
        made += await loans.installment_reminder()
        made += await petty_cash.unsettled_reminder()
    except Exception:  # noqa: BLE001
        logger.exception("Pengingat Fase 27 gagal")
    return made


async def build_tick() -> dict:
    """Fase 31: buka gerbang yang waktu tunggunya lewat, kirim pengingat, eskalasi telat."""
    import build_monitor as bm
    from engine import dispatch_pending
    try:
        out = await bm.tick()
        if out.get("escalations") or out.get("gates_opened"):
            await dispatch_pending()
        return out
    except Exception:  # noqa: BLE001
        logger.exception("Pemantauan jadwal pembangunan gagal")
        return {"schedules": 0}


async def bi_snapshot_tick() -> int:
    """Fase 44: snapshot metrik BI harian.

    Snapshot BUKAN kebenaran — ia selalu bisa dihitung ulang
    (`POST /api/analytics/snapshots/rebuild`) dan gate `verify_analytics` membandingkannya
    dengan hitungan langsung. Gunanya hanya supaya dashboard periode besar tidak menghitung
    ulang seluruh riwayat setiap kali dibuka.
    """
    import analytics_engine as ae
    try:
        return await ae.snapshot_tick()
    except Exception:  # noqa: BLE001
        logger.exception("Snapshot metrik BI gagal")
        return 0


async def build_weekly_report_tick() -> dict:
    """Fase 32: laporan mingguan pembangunan untuk direksi & manajer proyek.

    Dijalankan tiap Senin pagi WIB. Idempoten per pekan: bila sudah ada laporan untuk pekan
    tersebut, angkanya disegarkan tetapi notifikasi & tugas baca tidak dibuat ulang.
    """
    from db import ORG_ID
    import build_reports as br
    try:
        out = await br.run_weekly(ORG_ID, actor="system")
        if out.get("created"):
            logger.info("Laporan mingguan pembangunan %s: %s laporan baru",
                        out.get("week_key"), out.get("created"))
        return out
    except Exception:  # noqa: BLE001
        logger.exception("Laporan mingguan pembangunan gagal")
        return {"created": 0}


async def lead_rescore_tick() -> dict:
    """Fase 88B: skor lead yang diam turun tiap hari — bukan angka beku sejak hari pertama."""
    import lead_scoring
    try:
        return await lead_scoring.rescore_all()
    except Exception:  # noqa: BLE001
        logger.exception("Sapuan skor lead gagal")
        return {"total": 0, "changed": 0}


def register(scheduler) -> list:
    """Daftarkan job berkala fase inti. Semua jadwal UTC; komentar menyebut jam WIB."""
    jobs = [
        (lead_rescore_tick, {"trigger": "cron", "hour": 22, "minute": 30, "id": "lead_rescore"}),
        (finance_retention_tick, {"trigger": "interval", "seconds": 600,
                                  "id": "retention_sweep"}),
        (p27_reminder_tick, {"trigger": "interval", "seconds": 1800, "id": "p27_reminders"}),
        # Fase 31 — gerbang curing dibuka saat waktunya, pengingat H-1/hari-H, eskalasi telat.
        (build_tick, {"trigger": "interval", "seconds": 600, "id": "build_monitor"}),
        # Senin 00:05 UTC = Senin 07:05 WIB — laporan siap sebelum rapat pagi.
        (build_weekly_report_tick, {"trigger": "cron", "day_of_week": "mon", "hour": 0,
                                    "minute": 5, "id": "build_weekly_report"}),
        # 00:20 UTC = 07:20 WIB — snapshot BI sebelum jam kerja.
        (bi_snapshot_tick, {"trigger": "cron", "hour": 0, "minute": 20, "id": "bi_snapshot"}),
    ]
    for fn, kw in jobs:
        scheduler.add_job(fn, max_instances=1, coalesce=True, **kw)
    return [kw["id"] for _fn, kw in jobs]
