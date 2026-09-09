"""Kompresi + watermark foto (Fase 30b) — hemat kuota pembeli & foto bertanda asal.

Masalah nyata yang diperbaiki:
  * Foto lapangan diunggah langsung dari kamera HP (3–8 MB, sisi 4000 px). Portal pembeli
    dibuka lewat kuota seluler: galeri 6 foto bisa >20 MB dan lambat.
  * Foto progres yang dibagikan ke pembeli tidak punya penanda asal, sehingga bisa dipakai
    ulang di luar konteks (atau diklaim sebagai unit lain).
  * Foto HP membawa metadata EXIF termasuk **koordinat GPS** — ikut terkirim ke pembeli.

Yang dilakukan di sini (semua nyata, bukan simulasi):
  1. Putar gambar sesuai EXIF orientation (foto HP sering miring), lalu BUANG seluruh EXIF.
  2. Turunkan resolusi ke sisi terpanjang `PHOTO_MAX_DIM` (default 1600 px).
  3. Simpan JPEG progresif kualitas `PHOTO_QUALITY` (default 80) → ukuran turun drastis.
  4. Cap watermark: baris konteks (proyek/kavling) + organisasi + tanggal-jam WIB.
  5. Bangkitkan THUMBNAIL (`PHOTO_THUMB_DIM`, default 480 px) untuk grid galeri.

Aman by design: bila Pillow gagal memproses (format aneh/berkas rusak), fungsi
`optimize()` mengembalikan None dan pemanggil menyimpan berkas ASLI — unggahan tidak
pernah gagal hanya karena optimasi.
"""
import io
import logging
import os
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger("sipro.photo")

MAX_DIM = int(os.environ.get("PHOTO_MAX_DIM", "1600"))
QUALITY = int(os.environ.get("PHOTO_QUALITY", "80"))
THUMB_DIM = int(os.environ.get("PHOTO_THUMB_DIM", "480"))
THUMB_QUALITY = int(os.environ.get("PHOTO_THUMB_QUALITY", "68"))
WATERMARK_ON = os.environ.get("PHOTO_WATERMARK", "on").strip().lower() != "off"

IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic",
               "image/heif", "image/bmp", "image/tiff"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"}

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def is_image(content_type: str = None, filename: str = None) -> bool:
    """Apakah berkas ini gambar yang layak dioptimasi? (PDF/dokumen dilewati apa adanya)"""
    ct = (content_type or "").lower().split(";")[0].strip()
    if ct in IMAGE_TYPES:
        return True
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    return ext in IMAGE_EXTS


def _font(size: int):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:  # pragma: no cover - font rusak
                continue
    return ImageFont.load_default()


def wib_stamp(ts: datetime = None) -> str:
    """Cap waktu WIB yang dibaca manusia (data disimpan tetap UTC ISO)."""
    d = (ts or datetime.now(timezone.utc)).astimezone(timezone.utc) + timedelta(hours=7)
    return d.strftime("%d/%m/%Y %H:%M") + " WIB"


def _text_size(draw, text, font) -> tuple:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def stamp(img: Image.Image, lines: list) -> Image.Image:
    """Tempel bilah watermark semi-transparan di bawah gambar (teks putih, mudah dibaca)."""
    rows = [str(x).strip() for x in (lines or []) if str(x or "").strip()]
    if not rows or img.width < 240:
        return img
    size = max(11, int(img.width * 0.023))
    font = _font(size)
    pad = max(6, int(size * 0.55))
    draw = ImageDraw.Draw(img)
    heights, widths = [], []
    for r in rows:
        w, h = _text_size(draw, r, font)
        widths.append(w)
        heights.append(h)
    bar_h = sum(heights) + pad * (len(rows) + 1)
    overlay = Image.new("RGBA", (img.width, bar_h), (17, 24, 39, 150))
    img = img.convert("RGBA")
    img.alpha_composite(overlay, (0, img.height - bar_h))
    draw = ImageDraw.Draw(img)
    y = img.height - bar_h + pad
    for i, r in enumerate(rows):
        draw.text((pad, y), r, font=font, fill=(255, 255, 255, 235))
        y += heights[i] + pad
    return img.convert("RGB")


def _encode(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def optimize(data: bytes, *, watermark_lines: list = None, max_dim: int = None,
             quality: int = None, thumb_dim: int = None) -> dict:
    """Kompres + watermark + thumbnail. Mengembalikan None bila gambar tidak bisa diproses.

    Hasil: {data, thumb, content_type, width, height, size, thumb_size, original_size,
            watermark, optimized}
    """
    if not data:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:  # noqa: BLE001 - berkas rusak/format tak didukung
        logger.info("Optimasi foto dilewati (tidak bisa dibaca: %s)", e)
        return None
    try:
        img = ImageOps.exif_transpose(img)           # perbaiki orientasi kamera HP
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            conv = img.convert("RGBA")
            bg.paste(conv, mask=conv.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")                 # sekaligus membuang metadata EXIF
        limit = int(max_dim or MAX_DIM)
        if max(img.size) > limit:
            img.thumbnail((limit, limit), Image.LANCZOS)
        text = " · ".join(str(x).strip() for x in (watermark_lines or []) if str(x or "").strip())
        if WATERMARK_ON and watermark_lines:
            img = stamp(img, watermark_lines)
        full = _encode(img, int(quality or QUALITY))
        thumb_img = img.copy()
        thumb_img.thumbnail((int(thumb_dim or THUMB_DIM), int(thumb_dim or THUMB_DIM)),
                            Image.LANCZOS)
        thumb = _encode(thumb_img, THUMB_QUALITY)
    except Exception as e:  # noqa: BLE001 - jangan pernah menggagalkan unggahan
        logger.warning("Optimasi foto gagal (%s); berkas asli dipakai.", e)
        return None
    return {
        "data": full, "thumb": thumb, "content_type": "image/jpeg",
        "width": img.width, "height": img.height, "size": len(full),
        "thumb_size": len(thumb), "original_size": len(data),
        "watermark": (text if (WATERMARK_ON and text) else None),
        "optimized": True,
    }


def saving_pct(original: int, final: int) -> int:
    """Persentase penghematan ukuran (0 bila tidak menghemat) — dipakai UI & audit."""
    if not original or final >= original:
        return 0
    return int(round((original - final) * 100.0 / original))


def context_lines(*, org_name: str = None, context: str = None, when: datetime = None) -> list:
    """Susun baris watermark standar: konteks (proyek/kavling) lalu organisasi + waktu."""
    rows = []
    if context:
        rows.append(str(context)[:70])
    tail = " · ".join([x for x in [(org_name or "").strip()[:40], wib_stamp(when)] if x])
    rows.append(tail)
    return rows
