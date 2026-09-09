"""scheduler_p51.py — job berkala Fase 51 (pengingat WhatsApp otomatis).

Dipisah dari `engine.py` mengikuti pola `scheduler_p45/p46`: berkas itu sudah menyentuh batas
NFR 800 baris, jadi setiap job baru ditaruh di modul kecil yang mengimpor mesinnya secara
lokal (menghindari impor melingkar `wa_reminder_engine` → `notifications` → … → `engine`).

Kenapa satu kali sehari, bukan tiap jam: pengingat adalah pesan ke MANUSIA. Ambang batasnya
dihitung dalam HARI (H-3 jatuh tempo, 30 hari sisa garansi), jadi memeriksa lebih sering
hanya menambah risiko pesan ganda tanpa menambah manfaat. Dedup tetap dijaga index unik
(`uq_wa_reminder_dedup`), sehingga tombol "Jalankan sekarang" dan scheduler boleh bertemu.
"""
import logging

logger = logging.getLogger("sipro.scheduler.p51")


async def wa_reminder_tick() -> dict:
    """Pengingat garansi hampir habis, termin jatuh tempo, dan tunggakan."""
    import wa_reminder_engine as wre
    out = await wre.tick()
    if out:
        logger.info("Pengingat WA terkirim/simulasi: %s", out)
    return out


async def wa_outbox_tick() -> dict:
    """Fase 95F/97D — antrean kirim WhatsApp (broadcast) dengan batas laju & percobaan ulang."""
    import wa_outbox
    return await wa_outbox.tick()


def register(scheduler) -> list:
    jobs = [
        (wa_outbox_tick, {"trigger": "interval", "seconds": 10, "id": "wa_outbox_tick"}),
        # 01:00 UTC = 08:00 WIB — pembeli menerima pengingat di awal jam kerja, bukan tengah
        # malam. Jam kirim yang sopan adalah bagian dari kualitas pengingat.
        (wa_reminder_tick, {"trigger": "cron", "hour": 1, "minute": 0,
                            "id": "wa_reminder_daily"}),
    ]
    for fn, kw in jobs:
        scheduler.add_job(fn, max_instances=1, coalesce=True, **kw)
    return [kw["id"] for _fn, kw in jobs]
