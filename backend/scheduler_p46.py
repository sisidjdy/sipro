"""scheduler_p46.py — job berkala Fase 46 (kedaluwarsa izin yang menempel objek).

Dipisah dari `engine.py` (sudah di batas NFR 800 baris) dengan pola yang sama seperti
`scheduler_p45.py`: fungsi kecil yang mengimpor modulnya secara lokal.

Mengapa job ini perlu padahal sudah ada `permit_deadline_sweeper`?
  * Sweeper lama hanya melihat `deadline` (tenggat PENGURUSAN) dan hanya untuk izin yang
    BELUM disetujui. Izin yang sudah `approved` lalu **masa berlakunya habis** tidak pernah
    diperingatkan — padahal itu risiko terbesar (SLF kedaluwarsa → serah terima bermasalah).
  * Fase 46 menambahkan `expiry_at` + `scope` pada izin, jadi peringatannya bisa dikirim ke
    orang yang tepat dan menyebut objek yang tepat (proyek/cluster/blok/unit).
"""
import logging

logger = logging.getLogger("sipro.scheduler.p46")


async def permit_expiry_tick() -> int:
    """Peringatan masa berlaku izin: H-`reminder_days` dan setelah kedaluwarsa.

    Idempoten per hari per izin (`expiry_notified_on`) supaya pemakai tidak dibanjiri pesan
    yang sama lalu mematikan notifikasi.
    """
    import permit_alerts as pa
    made = await pa.expiry_tick()
    if made:
        logger.info("Peringatan kedaluwarsa izin dikirim: %s", made)
    return made
