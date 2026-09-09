"""DOKUMEN LAPANGAN & PENAGIHAN (Fase 62) — surat peringatan, berita acara, lampiran SPK.

Mesin cetaknya tetap SATU (`pdf_layout`, kop dari Pusat Konfigurasi Dokumen Fase 60).
Modul ini hanya merakit ISI tiga dokumen yang sebelumnya tidak pernah punya bentuk kertas:

  * **Surat Peringatan SP1/SP2/SP3** — angka & termin diambil dari surat yang sudah terbit
    (`warning_letters`), yang isinya berasal dari mesin denda. Tidak ada hitungan kedua.
  * **Berita Acara Opname** — rincian dari BARIS TERMIN yang sama dengan yang dipakai
    tagihan AP, termasuk yang DIKELUARKAN opname beserta alasannya. Berita acara yang
    menyembunyikan pekerjaan yang ditolak adalah berita acara yang berbohong.
  * **Punch list / daftar temuan** — untuk ditandatangani di lapangan; temuan yang sudah
    ditutup tetap tercetak dengan tanggal penutupan supaya bisa diperiksa ulang.

Ditambah **lampiran SPK**: gambar kerja & spesifikasi yang diunggah ke SPK dicetak sebagai
halaman lampiran pada SPK-nya, karena pasal 1 SPK menyebut "sesuai gambar dan spesifikasi
yang menjadi lampiran surat ini" — sebelum ini lampiran itu tidak pernah ada.
"""
import doc_layout as dl
import doc_script as ds
import pdf_layout as pl
import storage
from db import db

SP_TARGET = "SP"
BA_TARGET = "BA_OPNAME"
PUNCH_TARGET = "PUNCHLIST"

ATTACH_LABEL = {"gambar_kerja": "Gambar kerja", "spesifikasi": "Spesifikasi teknis",
                "lainnya": "Lampiran lain"}


def _rp(v) -> str:
    return "Rp " + f"{int(v or 0):,}".replace(",", ".")


def _tgl(iso) -> str:
    return str(iso or "")[:10] or "-"


# ==================================================== surat peringatan tunggakan
def sp_clauses(letter: dict) -> list:
    level = int(letter.get("level") or 1)
    batas = letter.get("threshold_months") or 2
    umum = [
        f"Pembayaran wajib dilunasi paling lambat {letter.get('deadline_days')} hari "
        "kalender sejak tanggal surat ini.",
        "Denda keterlambatan tetap berjalan atas termin yang belum dibayar sesuai ketentuan "
        "yang tercantum pada Surat Pesanan Rumah.",
        "Bila pembayaran terhambat karena keadaan tertentu, Saudara/i DAPAT mengajukan "
        "keringanan atau penjadwalan ulang secara tertulis kepada Manajer Keuangan sebelum "
        "tenggat di atas berakhir.",
    ]
    if level == 1:
        return umum + ["Surat ini adalah peringatan PERTAMA dan belum menghapus hak apa pun "
                       "yang Saudara/i miliki atas unit yang dipesan."]
    if level == 2:
        return umum + [
            "Ini adalah peringatan KEDUA. Bila tunggakan tidak diselesaikan, akan diterbitkan "
            "Surat Peringatan Ketiga yang memuat pemberitahuan hak pembatalan sepihak.",
            "Pekerjaan pembangunan dan/atau proses legal atas unit dapat ditunda selama "
            "tunggakan berlangsung."]
    return umum + [
        f"Ini adalah peringatan KETIGA dan TERAKHIR. Sesuai Surat Pesanan Rumah, tunggakan "
        f"{batas} bulan memberi hak kepada Pengembang untuk membatalkan pesanan secara "
        "sepihak.",
        "Pembatalan tidak terjadi otomatis: keputusannya diambil Manajer Keuangan atas "
        "pengajuan Manajer Sales, dan Saudara/i akan diberitahu tertulis beserta perhitungan "
        "pengembalian dana (bila ada) sesuai pasal pembatalan.",
        "Selama belum ada keputusan pembatalan, pelunasan tunggakan tetap dapat dilakukan "
        "dan menggugurkan proses ini."]


def sp_content(letter: dict) -> dict:
    meta = [
        ("Nomor surat", letter.get("number") or "-"),
        ("Tingkat peringatan", letter.get("level_label") or "-"),
        ("Kepada", letter.get("buyer_name") or "-"),
        ("Alamat", letter.get("buyer_address") or "-"),
        ("Unit / kavling", letter.get("unit_code") or "-"),
        ("Nomor kontrak", letter.get("contract_number") or "belum berkontrak"),
        ("Lama tunggakan", f"{letter.get('months_in_arrears')} bulan "
                           f"(keterlambatan terlama {letter.get('max_days_late')} hari)"),
        ("Jumlah tertunggak", _rp(letter.get("overdue_amount"))),
        ("Denda berjalan", _rp(letter.get("denda_running"))),
    ]
    kolom = ["Termin", "Jatuh tempo", "Hari terlambat", "Sisa kewajiban"]
    baris = [[t.get("label") or "-", _tgl(t.get("due_date")), str(t.get("days_late") or 0),
              _rp(t.get("outstanding"))] for t in (letter.get("terms") or [])]
    total = ["", "", "Total tertunggak", _rp(letter.get("overdue_amount"))]
    isi = (
        "Dengan hormat,\n"
        "Berdasarkan catatan pembayaran kami, kewajiban Saudara/i atas unit tersebut di atas "
        "belum diselesaikan sampai tanggal surat ini diterbitkan. Rincian termin yang "
        "tertunggak — dihitung SESUDAH masa toleransi kontrak, bukan sejak hari jatuh tempo — "
        "kami sampaikan pada tabel berikut."
    )
    return {
        "title": f"SURAT PERINGATAN {letter.get('level')} (SP{letter.get('level')})",
        "doc_number": letter.get("number"), "meta": meta, "content": isi,
        "item_table": (kolom, baris, total) if baris else None,
        "note": ("Surat ini diterbitkan dari data tagihan sistem pada "
                 f"{_tgl(letter.get('created_at'))}. Bila Saudara/i sudah membayar tetapi "
                 "belum tercatat, kirimkan bukti transfer melalui portal pembeli agar "
                 "diperiksa."),
    }


async def sp_pdf(org: str, letter: dict, issuer: dict) -> bytes:
    layout = await dl.get_layout(org, SP_TARGET)
    layout.setdefault("options", {})["doc_date"] = _tgl(letter.get("created_at"))
    imgs = await dl.images(org, layout)
    sigs = dl.signatures_for(layout, issuer_name=issuer.get("name"),
                             issuer_position=issuer.get("role"))
    if len(sigs) > 1:
        sigs[1] = {**sigs[1], "title": "Diterima oleh (Pembeli)",
                   "name": letter.get("buyer_name") or ""}
    isi = sp_content(letter)
    # Fase 66: naskah pemakai untuk jenis dokumen ini tercetak sebagai pembuka.
    pembuka = await ds.intro_for(org, SP_TARGET, {
        "doc_number": isi["doc_number"], "date": _tgl(letter.get("created_at")),
        "org_name": (layout.get("brand") or {}).get("company_name") or "",
        "sales_name": issuer.get("name") or ""})
    isi_naskah = "\n\n".join(x for x in [pembuka, isi["content"]] if x.strip())
    return pl.render_letter(layout, imgs, title=isi["title"], doc_number=isi["doc_number"],
                            content=isi_naskah, meta=isi["meta"],
                            item_table=isi["item_table"], clauses=sp_clauses(letter),
                            note=isi["note"], signatures_override=sigs)


# ==================================================== berita acara opname termin
BA_CLAUSES = [
    "Berita acara ini menyatakan hasil pemeriksaan lapangan (opname) atas pekerjaan yang "
    "diajukan pada termin tersebut di atas.",
    "Pekerjaan yang DIKELUARKAN dari termin ini tercantum beserta alasannya dan dapat "
    "diajukan kembali pada termin berikutnya setelah diperbaiki.",
    "Nilai yang tercantum adalah nilai borongan pekerjaan yang lolos pemeriksaan; retensi "
    "ditahan sesuai SPK dan dicairkan setelah masa pemeliharaan berakhir.",
    "Kedua pihak menandatangani berita acara ini sebagai dasar penerbitan tagihan.",
]


def ba_content(claim: dict, spk: dict) -> dict:
    lines = claim.get("lines") or []
    lolos = [ln for ln in lines if ln.get("included", True)]
    ditolak = [ln for ln in lines if not ln.get("included", True)]
    bruto = int(claim.get("gross") or claim.get("gross_est") or 0)
    ret_pct = float(spk.get("retention_pct") or 0)
    retensi = int(claim.get("retention_held") or round(bruto * ret_pct / 100))
    meta = [
        ("Nomor berita acara", claim.get("claim_number") or "-"),
        ("SPK", f"{spk.get('spk_number') or '-'} — {spk.get('title') or ''}".strip(" —")),
        ("Subkontraktor", spk.get("subcontractor_name") or "-"),
        ("Proyek", spk.get("project_name") or claim.get("project_name") or "-"),
        ("Dasar tagihan", "Per item berbukti" if claim.get("basis") == "items"
                          else "Lump-sum (persen)"),
        ("Progres", f"{claim.get('prev_pct') or 0}% → "
                    f"{claim.get('verified_pct') or claim.get('claimed_pct') or 0}%"),
        ("Diperiksa oleh", claim.get("verified_by") or "belum di-opname"),
        ("Tanggal opname", _tgl(claim.get("verified_at") or claim.get("created_at"))),
        ("Nilai lolos opname", _rp(bruto)),
        ("Retensi ditahan", f"{ret_pct:g}% ({_rp(retensi)})"),
        ("Dibayarkan (netto)", _rp(claim.get("net") or (bruto - retensi))),
    ]
    kolom = ["Unit", "Kode", "Pekerjaan", "Hasil opname", "Nilai"]
    baris = [[ln.get("unit_code") or "-", ln.get("step_code") or "-",
              ln.get("step_name") or "-", "LOLOS", _rp(ln.get("value"))] for ln in lolos]
    baris += [[ln.get("unit_code") or "-", ln.get("step_code") or "-",
               ln.get("step_name") or "-",
               f"DIKELUARKAN — {ln.get('exclude_reason') or 'tanpa catatan'}",
               _rp(ln.get("value"))] for ln in ditolak]
    total = ["", "", "", "Nilai lolos opname", _rp(bruto)]
    catatan = claim.get("note") or ""
    return {
        "title": "BERITA ACARA OPNAME PEKERJAAN",
        "doc_number": claim.get("claim_number"), "meta": meta,
        "content": (f"Catatan pemeriksaan :\n{catatan}" if catatan else ""),
        "item_table": (kolom, baris, total) if baris else None,
        "note": (f"{len(ditolak)} pekerjaan dikeluarkan dari termin ini "
                 f"({_rp(sum(int(ln.get('value') or 0) for ln in ditolak))}). "
                 "Pekerjaan tersebut belum hilang: ajukan kembali setelah diperbaiki."),
    }


async def ba_pdf(org: str, claim: dict, spk: dict, issuer: dict) -> bytes:
    layout = await dl.get_layout(org, BA_TARGET)
    layout.setdefault("options", {})["doc_date"] = _tgl(
        claim.get("verified_at") or claim.get("created_at"))
    draf = claim.get("status") in ("submitted", "draft")
    if draf:
        layout["brand"] = {**(layout.get("brand") or {}),
                           "watermark_text": "DRAFT — BELUM DI-OPNAME",
                           "watermark_file_id": None, "watermark_opacity": 12}
    imgs = await dl.images(org, layout)
    sigs = dl.signatures_for(layout, issuer_name=claim.get("verified_by") or issuer.get("name"),
                             issuer_position="Manajer Proyek / Pengawas")
    if sigs:
        sigs[0] = {**sigs[0], "title": "Pihak Pertama (Pengawas Pekerjaan)"}
    if len(sigs) > 1:
        sigs[1] = {**sigs[1], "title": "Pihak Kedua (Subkontraktor)",
                   "name": spk.get("subcontractor_name") or ""}
    isi = ba_content(claim, spk)
    # Fase 66: naskah pemakai untuk jenis dokumen ini tercetak sebagai pembuka.
    pembuka = await ds.intro_for(org, BA_TARGET, {
        "doc_number": isi["doc_number"], "date": (layout.get("options") or {}).get("doc_date") or "",
        "org_name": (layout.get("brand") or {}).get("company_name") or "",
        "sales_name": issuer.get("name") or ""})
    isi_naskah = "\n\n".join(x for x in [pembuka, isi["content"]] if x.strip())
    return pl.render_letter(layout, imgs, title=isi["title"], doc_number=isi["doc_number"],
                            content=isi_naskah, meta=isi["meta"],
                            item_table=isi["item_table"], clauses=BA_CLAUSES,
                            note=isi["note"], signatures_override=sigs)


# ==================================================== berita acara punch list
PUNCH_CLAUSES = [
    "Daftar temuan ini diperiksa bersama di lokasi; setiap temuan yang dinyatakan SELESAI "
    "wajib disertai bukti perbaikan (foto sesudah) pada sistem.",
    "Temuan yang masih terbuka menjadi tanggung jawab pihak pelaksana sampai dinyatakan "
    "selesai dan diverifikasi pengawas.",
    "Temuan terbuka pada unit yang menjadi lingkup SPK menahan pencairan retensi "
    "subkontraktor sesuai ketentuan masa pemeliharaan.",
]


def punch_content(rows: list, ctx: dict) -> dict:
    terbuka = [r for r in rows if r.get("status") in ("open", "in_progress")]
    meta = [
        ("Proyek", ctx.get("project_name") or "seluruh proyek yang menjadi kewenangan"),
        ("Kavling", ctx.get("unit_code") or "seluruh kavling"),
        ("Jumlah temuan", str(len(rows))),
        ("Belum selesai", str(len(terbuka))),
        ("Prioritas tinggi belum selesai",
         str(sum(1 for r in terbuka if r.get("severity") == "high"))),
        ("Tanggal cetak", _tgl(ctx.get("today"))),
    ]
    kolom = ["Temuan", "Lokasi", "Prioritas", "Status", "Tenggat", "Bukti perbaikan"]
    baris = [[r.get("title") or "-", r.get("location") or "-",
              str(r.get("severity") or "-"), str(r.get("status") or "-"),
              _tgl(r.get("due_date")),
              f"{len(r.get('fix_photos') or [])} foto"
              + (f" · selesai {_tgl(r.get('closed_at'))}" if r.get("closed_at") else "")]
             for r in rows]
    return {
        "title": "BERITA ACARA PEMERIKSAAN & DAFTAR TEMUAN (PUNCH LIST)",
        "doc_number": ctx.get("doc_number") or "", "meta": meta,
        "content": ("Pemeriksaan bersama dilakukan atas pekerjaan pada lokasi tersebut di "
                    "atas. Temuan yang disepakati untuk diperbaiki tercantum pada tabel "
                    "berikut beserta tenggat penyelesaiannya."),
        "item_table": (kolom, baris, None) if baris else None,
        "note": ("Daftar ini dicetak dari catatan lapangan sistem. Temuan tanpa foto bukti "
                 "perbaikan TIDAK dianggap selesai walaupun statusnya sudah diubah."),
    }


async def punch_pdf(org: str, rows: list, ctx: dict, issuer: dict) -> bytes:
    layout = await dl.get_layout(org, PUNCH_TARGET)
    layout.setdefault("options", {})["doc_date"] = _tgl(ctx.get("today"))
    imgs = await dl.images(org, layout)
    sigs = dl.signatures_for(layout, issuer_name=issuer.get("name"),
                             issuer_position=issuer.get("role"))
    if sigs:
        sigs[0] = {**sigs[0], "title": "Pengawas / Pelaksana Lapangan"}
    if len(sigs) > 1:
        sigs[1] = {**sigs[1], "title": "Pihak Pelaksana (Subkontraktor)"}
    isi = punch_content(rows, ctx)
    # Fase 66: naskah pemakai untuk jenis dokumen ini tercetak sebagai pembuka.
    pembuka = await ds.intro_for(org, PUNCH_TARGET, {
        "doc_number": isi["doc_number"], "date": _tgl(ctx.get("today")),
        "org_name": (layout.get("brand") or {}).get("company_name") or "",
        "sales_name": issuer.get("name") or ""})
    isi_naskah = "\n\n".join(x for x in [pembuka, isi["content"]] if x.strip())
    return pl.render_letter(layout, imgs, title=isi["title"], doc_number=isi["doc_number"],
                            content=isi_naskah, meta=isi["meta"],
                            item_table=isi["item_table"], clauses=PUNCH_CLAUSES,
                            note=isi["note"], signatures_override=sigs)


# ==================================================== lampiran SPK (gambar & spesifikasi)
async def spk_attachments(org: str, spk_id: str) -> list:
    return await db.spk_attachments.find(
        {"org_id": org, "spk_id": spk_id, "is_deleted": {"$ne": True}},
        {"_id": 0}).sort("created_at", 1).to_list(50)


async def attachment_pages(org: str, spk_id: str) -> list:
    """Halaman lampiran SPK: daftar berkas + gambar yang bisa dirender apa adanya.

    Berkas yang hilang di penyimpanan TIDAK menggagalkan pencetakan SPK — ia tetap
    tercantum pada daftar (supaya ketiadaannya kelihatan) tanpa gambar.
    """
    rows = await spk_attachments(org, spk_id)
    if not rows:
        return []
    daftar, gambar = [], []
    for i, a in enumerate(rows, 1):
        rec = await db.files.find_one({"id": a.get("file_id"), "org_id": org,
                                       "is_deleted": False}, {"_id": 0}) or {}
        daftar.append([str(i), ATTACH_LABEL.get(a.get("kind"), a.get("kind") or "-"),
                       a.get("label") or rec.get("original_filename") or "-",
                       rec.get("original_filename") or "berkas tidak ditemukan",
                       _tgl(a.get("created_at"))])
        if not rec or not str(rec.get("content_type") or "").startswith("image/"):
            continue
        try:
            data, _ct = await storage.get_file_bytes(rec["storage_path"], rec.get("provider"))
            gambar.append({"caption": f"Lampiran {i} — "
                                      f"{a.get('label') or rec.get('original_filename')}",
                           "data": data})
        except (FileNotFoundError, OSError, KeyError):
            continue
    return [{
        "title": "LAMPIRAN SPK — GAMBAR KERJA & SPESIFIKASI",
        "note": ("Lampiran ini adalah bagian tidak terpisahkan dari SPK. Pekerjaan yang "
                 "menyimpang dari gambar/spesifikasi di bawah bukan dasar penagihan."),
        "table": (["No", "Jenis", "Judul", "Berkas", "Diunggah"], daftar),
        "images": gambar,
    }]
