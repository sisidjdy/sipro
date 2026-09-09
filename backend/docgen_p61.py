"""CETAK SPK SUBKONTRAKTOR & PO PENGADAAN (Fase 61).

Sampai Fase 60, dua dokumen yang paling sering DIPEGANG ORANG LUAR justru tidak punya
bentuk cetak: Surat Perintah Kerja (yang ditandatangani subkontraktor sebelum bekerja) dan
Purchase Order (yang dipegang vendor sebagai dasar mengirim barang & menagih). Keduanya
hanya ada sebagai baris di layar, sehingga di lapangan diganti WhatsApp — dan pekerjaan
tanpa surat adalah pekerjaan tanpa dasar tagihan.

Modul ini merakit ISI kedua dokumen (bukan mesin cetaknya): mesin cetaknya tetap SATU,
`pdf_layout`, dengan kop/footer/tanda tangan dari Pusat Konfigurasi Dokumen (Fase 60).

Dua aturan yang dijaga di sini:
  1. **Dokumen yang belum disetujui bertanda DRAFT.** PO berstatus `draft` dan SPK berstatus
     `draft` dicetak dengan watermark "DRAFT — BELUM DISETUJUI" supaya tidak dipakai vendor
     sebagai dasar mengirim barang.
  2. **Angka dokumen = angka database.** Rincian item dan totalnya dibaca dari baris yang
     sama dengan yang dipakai penagihan (lingkup SPK & item PO), tidak dihitung ulang di
     sini dengan rumus kedua.
"""
import doc_layout as dl
import doc_script as ds
import opname as op
import pdf_layout as pl
from db import db

SPK_TARGET = "SPK"
PO_TARGET = "PO"

SPK_CLAUSES = [
    "Pihak Kedua melaksanakan pekerjaan sesuai lingkup, gambar, dan spesifikasi yang menjadi "
    "lampiran surat ini.",
    "Pembayaran dilakukan per termin berdasarkan pekerjaan yang SUDAH DIVERIFIKASI "
    "(opname berbukti), bukan berdasarkan persen yang diajukan sepihak.",
    "Retensi ditahan dari setiap termin dan dicairkan setelah masa pemeliharaan berakhir "
    "serta seluruh perbaikan (defect) dinyatakan selesai.",
    "Perubahan lingkup atau nilai pekerjaan hanya sah melalui Change Order tertulis.",
    "Pihak Kedua bertanggung jawab atas keselamatan kerja (K3), kebersihan area, dan "
    "perbaikan kerusakan yang ditimbulkan pekerjaannya.",
]

PO_CLAUSES = [
    "Barang/jasa dikirim sesuai jenis, jumlah, dan spesifikasi pada rincian di atas.",
    "Penerimaan barang dicatat melalui Bukti Penerimaan Barang (GRN); barang yang tidak "
    "dicatat sebagai diterima tidak dapat ditagihkan.",
    "Tagihan wajib menyebut nomor PO ini dan hanya dibayar setelah lolos pencocokan "
    "tiga arah (PO — penerimaan — tagihan).",
    "Barang yang tidak sesuai spesifikasi akan dikembalikan atas biaya penyedia.",
]


def _draft_layout(layout: dict, draft: bool, label: str) -> dict:
    """Tandai dokumen yang BELUM disetujui — tanda ini tidak boleh bisa dimatikan pemakai."""
    if not draft:
        return layout
    out = dict(layout)
    out["brand"] = {**(layout.get("brand") or {}), "watermark_text": label,
                    "watermark_file_id": None, "watermark_opacity": 12}
    return out


def _rp(v) -> str:
    return "Rp " + f"{int(v or 0):,}".replace(",", ".")


def _tanggal(iso: str) -> str:
    return (iso or "")[:10] or "-"


def spk_content(spk: dict, scope: list) -> dict:
    """Isi SPK: identitas para pihak, nilai, dan RINCIAN lingkup pekerjaan bila ada."""
    s = op.summarize(scope) if scope else {}
    retensi = round(int(spk.get("contract_value") or 0)
                    * float(spk.get("retention_pct") or 0) / 100)
    meta = [
        ("Nomor SPK", spk.get("spk_number") or "-"),
        ("Pekerjaan", spk.get("title") or "-"),
        ("Subkontraktor (Pihak Kedua)", spk.get("subcontractor_name") or "-"),
        ("Proyek", spk.get("project_name") or "-"),
        ("Jangka waktu", f"{_tanggal(spk.get('start_date'))} s/d "
                         f"{_tanggal(spk.get('end_date'))}"),
        ("Nilai kontrak", _rp(spk.get("contract_value"))),
        ("Retensi", f"{spk.get('retention_pct') or 0}% ({_rp(retensi)})"),
        ("Masa pemeliharaan", f"{spk.get('maintenance_days') or 0} hari setelah selesai"),
    ]
    columns = ["Unit", "Kode", "Pekerjaan", "Nilai borongan"]
    rows = [[r.get("unit_code") or "-", r.get("step_code") or "-",
             r.get("step_name") or "-", _rp(r.get("value"))] for r in scope]
    total = ["", "", "Total lingkup", _rp(s.get("scope_value"))] if scope else None
    isi = spk.get("scope") or ""
    if not scope and isi:
        isi = f"Lingkup pekerjaan :\n{isi}"
    return {
        "title": "SURAT PERINTAH KERJA (SPK)",
        "doc_number": spk.get("spk_number"),
        "meta": meta,
        "content": isi,
        "item_table": (columns, rows, total) if scope else None,
        "note": ("Progres dan pembayaran SPK ini mengikuti pekerjaan yang terverifikasi pada "
                 f"sistem (saat dicetak: {spk.get('progress_pct') or 0}%)."),
    }


def po_content(po: dict) -> dict:
    """Isi PO: penyedia, jenis, jatuh tempo, dan rincian item + total."""
    meta = [
        ("Nomor PO", po.get("po_number") or "-"),
        ("Penyedia", po.get("vendor") or po.get("subcontractor_name") or "-"),
        ("Proyek", po.get("project_name") or "-"),
        ("Jenis pengadaan", str(po.get("po_type") or "-")),
        ("Tanggal PO", _tanggal(po.get("created_at"))),
        ("Jatuh tempo kirim", _tanggal(po.get("due_date"))),
    ]
    if po.get("spk_id"):
        meta.append(("Dasar SPK", po.get("spk_id")))
    columns = ["Uraian", "Satuan", "Jumlah", "Harga satuan", "Nilai"]
    rows = [[it.get("description") or "-", it.get("uom") or "-",
             f"{it.get('qty') or 0:g}", _rp(it.get("unit_price")), _rp(it.get("amount"))]
            for it in (po.get("items") or [])]
    total = ["", "", "", "Total PO", _rp(po.get("total"))]
    return {
        "title": "PURCHASE ORDER (PO)",
        "doc_number": po.get("po_number"),
        "meta": meta,
        "content": (f"Catatan : {po['note']}" if po.get("note") else ""),
        "item_table": (columns, rows, total),
        "note": ("PO ini sah setelah disetujui pejabat berwenang; penerimaan barang wajib "
                 "dicatat sebagai GRN sebelum tagihan diproses."),
    }


async def render(org: str, *, target: str, isi: dict, clauses: list, draft: bool,
                 draft_label: str, issuer: dict, tanggal: str = None,
                 counterparty: tuple = None, attachment_pages: list = None) -> bytes:
    """Rakit PDF-nya dengan mesin cetak & kop yang SAMA dengan dokumen lain."""
    layout = await dl.get_layout(org, target)
    layout.setdefault("options", {})["doc_date"] = tanggal or ""
    layout = _draft_layout(layout, draft, draft_label)
    imgs = await dl.images(org, layout)
    sigs = dl.signatures_for(layout, issuer_name=issuer.get("name"),
                             issuer_position=issuer.get("role"))
    if counterparty and len(sigs) > 1:
        judul, nama = counterparty
        # Pihak kedua dokumen ini BUKAN pemesan rumah: yang menandatangani adalah
        # subkontraktor/penyedia, dan namanya sudah diketahui sistem — tidak perlu
        # dibiarkan kosong untuk diisi tangan.
        sigs[1] = {**sigs[1], "title": judul, "name": nama or sigs[1].get("name")}
    # Fase 66: naskah yang ditulis pemakai untuk jenis dokumen ini tercetak sebagai
    # PEMBUKA di atas rincian yang dirakit sistem — naskah tidak lagi berhenti di layar.
    pembuka = await ds.intro_for(org, target, {
        "doc_number": isi.get("doc_number") or "", "date": tanggal or "",
        "org_name": (layout.get("brand") or {}).get("company_name") or "",
        "sales_name": issuer.get("name") or ""})
    isi_naskah = "\n\n".join(x for x in [pembuka, isi.get("content") or ""] if x.strip())
    return pl.render_letter(
        layout, imgs, title=isi["title"], doc_number=isi.get("doc_number") or "",
        content=isi_naskah, meta=isi.get("meta"),
        item_table=isi.get("item_table"), clauses=clauses,
        note=isi.get("note") or "", signatures_override=sigs,
        attachment_pages=attachment_pages)


async def spk_pdf(org: str, spk: dict, issuer: dict) -> bytes:
    scope = await op.scope_rows(org, spk["id"])
    isi = spk_content(spk, scope)
    # Fase 62: pasal 1 SPK menyebut gambar & spesifikasi "yang menjadi lampiran surat ini" —
    # lampirannya kini benar-benar tercetak bersama suratnya.
    import docgen_p62 as p62
    lampiran = await p62.attachment_pages(org, spk["id"])
    return await render(org, target=SPK_TARGET, isi=isi, clauses=SPK_CLAUSES,
                        attachment_pages=lampiran,
                        draft=spk.get("status") == "draft",
                        draft_label="DRAFT — BELUM BERLAKU", issuer=issuer,
                        tanggal=_tanggal(spk.get("start_date")),
                        counterparty=("Pihak Kedua (Subkontraktor)",
                                      spk.get("subcontractor_name")))


async def po_pdf(org: str, po: dict, issuer: dict) -> bytes:
    isi = po_content(po)
    if po.get("spk_id"):
        spk = await db.spk.find_one({"id": po["spk_id"], "org_id": org},
                                    {"_id": 0, "spk_number": 1, "title": 1})
        if spk:
            isi["meta"] = [(k, f"{spk.get('spk_number')} — {spk.get('title') or ''}".strip(" —")
                            if k == "Dasar SPK" else v) for k, v in isi["meta"]]
    return await render(org, target=PO_TARGET, isi=isi, clauses=PO_CLAUSES,
                        draft=po.get("status") == "draft",
                        draft_label="DRAFT — BELUM DISETUJUI", issuer=issuer,
                        tanggal=_tanggal(po.get("created_at")),
                        counterparty=("Pihak Kedua (Penyedia)",
                                      po.get("vendor") or po.get("subcontractor_name")))
