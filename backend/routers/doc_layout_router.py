"""ROUTER KONFIGURASI TAMPILAN DOKUMEN (Fase 60) — prefix `/doc-layouts`.

Bukan menu baru: dipakai oleh tab **Master Data → Template Dokumen** yang sudah ada.
Prefix sendiri (bukan di bawah `/documents`) karena `documents_router` punya jalur
`/{doc_id}` yang akan menelan sub-jalur baru sebagai id dokumen.

Pemisahan tugas: MEMBACA konfigurasi = `documents:view`; MENGUBAH & PRATINJAU dengan
rancangan yang belum disimpan = `settings:update`. Kop surat & identitas perusahaan adalah
pengaturan ORGANISASI — sales yang boleh menerbitkan dokumen tidak boleh mengubah wajah
seluruh dokumen perusahaan.
"""
from fastapi import APIRouter, Depends, HTTPException, Response

import doc_layout as dl
import doc_script as ds
import pdf_layout as pl
from core_utils import serialize_doc
from db import ORG_ID, db
from models_p60 import DocLayoutSave, DocPreviewIn, DocScriptSave
from rbac import audit_log, require_permission

router = APIRouter(prefix="/doc-layouts", tags=["doc-layouts"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


async def _ensure_code(org: str, code: str) -> None:
    """Fase 66: kode yang sah = terdaftar di TARGETS ATAU punya naskah sendiri."""
    if not await dl.known_code(org, code):
        raise HTTPException(status_code=404, detail=f"Dokumen '{code}' tidak dikenal.")


@router.get("")
async def list_layouts(user: dict = Depends(require_permission("documents", "view"))):
    """Daftar dokumen yang bisa dikonfigurasi + mana yang sudah disesuaikan."""
    return {"data": await dl.list_targets(_org(user)),
            "money_rows_catalog": [{"code": c, "label": lbl} for c, lbl in dl.MONEY_ROWS],
            "sections_catalog": [{"key": k, "label": lbl} for k, lbl in dl.SECTIONS]}


@router.get("/{code}")
async def get_layout(code: str, user: dict = Depends(require_permission("documents", "view"))):
    await _ensure_code(_org(user), code)
    return {"data": serialize_doc(await dl.get_layout(_org(user), code))}


@router.put("/{code}")
async def save_layout(code: str, payload: DocLayoutSave,
                      user: dict = Depends(require_permission("settings", "update"))):
    await _ensure_code(_org(user), code)
    out = await dl.save_layout(_org(user), code, payload.model_dump(exclude_none=True),
                               user.get("email"))
    await audit_log(user, "update", "document_layouts", code,
                    {"sections": len(out.get("sections") or []),
                     "signatures": len(out.get("signatures") or [])})
    return {"data": serialize_doc(out)}


@router.delete("/{code}")
async def reset_layout(code: str,
                       user: dict = Depends(require_permission("settings", "update"))):
    """Kembalikan ke bawaan — dokumen yang sudah terbit tidak ikut berubah."""
    await _ensure_code(_org(user), code)
    out = await dl.reset_layout(_org(user), code)
    await audit_log(user, "delete", "document_layouts", code)
    return {"data": serialize_doc(out)}


# ------------------------------------------------ NASKAH per jenis dokumen (Fase 66)
@router.get("/{code}/script")
async def get_script(code: str,
                     user: dict = Depends(require_permission("documents", "view"))):
    """Naskah + daftar placeholder yang SAH untuk jenis dokumen ini."""
    org = _org(user)
    await _ensure_code(org, code)
    label = dl.TARGETS.get(code, (code, "letter"))[0]
    return {"data": await ds.get_script(org, code, label=label)}


@router.put("/{code}/script")
async def put_script(code: str, payload: DocScriptSave,
                    user: dict = Depends(require_permission("settings", "update"))):
    """Simpan naskah. Placeholder asing DITOLAK — dokumen resmi tidak boleh tercetak
    dengan `{{apa_saja}}` mentah di tangan pembeli atau bank.

    Izin: `settings:update` — naskah adalah TEKS RESMI perusahaan (sama kelasnya dengan kop
    surat), bukan isi satu transaksi. Sales yang boleh menerbitkan dokumen tidak boleh
    mengubah kalimat pasal yang mengikat perusahaan.
    """
    org = _org(user)
    await _ensure_code(org, code)
    try:
        out = await ds.save_script(org, code, payload.content, user.get("email"),
                                   name=payload.name
                                   or dl.TARGETS.get(code, (None,))[0])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "document_templates", code,
                    {"length": len(payload.content or "")})
    return {"data": out, "message": "Naskah dokumen disimpan."}


@router.post("/{code}/preview")
async def preview(code: str, payload: DocPreviewIn, document_id: str = None,
                  user: dict = Depends(require_permission("settings", "update"))):
    """PDF pratinjau dari rancangan yang BELUM disimpan — mesin cetak yang sama.

    `document_id` opsional: pratinjau memakai DATA NYATA dokumen yang sudah terbit, supaya
    pemakai tidak menebak bagaimana konfigurasinya bekerja pada dokumen sungguhan.
    """
    await _ensure_code(_org(user), code)
    org = _org(user)
    rancangan = payload.model_dump(exclude_none=True)
    naskah_draf = rancangan.pop("script", None)
    layout = dl._merge(await dl.get_layout(org, code), rancangan)
    imgs = await dl.images(org, layout)
    contoh = dl.sample_document(layout)
    # NASKAH ikut dirender: pratinjau harus memperlihatkan isi dokumen, bukan hanya kop.
    naskah = naskah_draf if naskah_draf is not None else (
        await ds.get_script(org, code))["content"]
    naskah_contoh = ds.sample_script(code, naskah)
    if (layout.get("kind") or "letter") == "table":
        if code == "INVOICE":
            pdf = pl.render_table(
                layout, imgs, title="INVOICE CONTOH — Tagihan Pembayaran Unit",
                subtitle="Pembeli: Budi Santoso · Unit: A-12 · Sudah dibayar: Rp 50.000.000 · Sisa: Rp 700.000.000",
                columns=["Termin", "Jatuh tempo", "Jumlah", "Dibayar", "Status"],
                rows=[["Booking fee", "2026-01-10", "Rp 5.000.000", "Rp 5.000.000", "Lunas"],
                      ["Uang muka (DP)", "2026-02-10", "Rp 45.000.000", "Rp 45.000.000", "Lunas"],
                      ["Pelunasan / pencairan KPR", "2026-04-10", "Rp 700.000.000", "Rp 0", "Belum jatuh tempo"]],
                total_row=["TOTAL", "", "Rp 750.000.000", "Rp 50.000.000", ""], intro=naskah_contoh,
                note="Pratinjau dengan data contoh — bukan invoice sungguhan.")
            return Response(content=pdf, media_type="application/pdf")
        pdf = pl.render_table(
            layout, imgs, title="LAPORAN CONTOH — Aging Piutang",
            subtitle="Pratinjau tampilan laporan tabel", columns=["Kategori umur", "Nilai"],
            rows=[["Lancar", "Rp 1.250.000.000"], ["1-30 hari", "Rp 212.500.000"],
                  ["31-60 hari", "Rp 0"]],
            total_row=["Total", "Rp 1.462.500.000"], intro=naskah_contoh,
            note="Pratinjau dengan data contoh — bukan laporan sungguhan.")
        return Response(content=pdf, media_type="application/pdf")

    title, number, meta, content, clauses, note = (
        (dl.TARGETS.get(code, (contoh["title"],))[0] if code != dl.DEFAULT_CODE
         else contoh["title"]).upper(),
        contoh["doc_number"], contoh["meta"], naskah_contoh, contoh["clauses"],
        contoh["note"])
    amounts = contoh["amounts"]
    if document_id:
        doc = await db.documents.find_one({"id": document_id, "org_id": org}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan.")
        snap = doc.get("context_snapshot") or {}
        title, number, content = (doc.get("title") or title), doc.get("doc_number"), \
            doc.get("content") or ""
        meta = [("Pemesan", snap.get("customer_name") or "-"),
                ("Unit", snap.get("unit_block") or "-"),
                ("Proyek", snap.get("property_name") or "-")]
        amounts, clauses, note = {}, None, "Pratinjau memakai data dokumen nyata."
        if doc.get("contract_id"):
            import contracts_engine as ce
            import docgen as dg
            try:
                amounts = dg.layout_amounts(
                    await ce.build_breakdown(org, await ce.get_raw(org, doc["contract_id"])))
            except Exception:
                amounts = {}
    rows = dl.money_rows_for(layout, amounts) if amounts else []
    sigs = dl.signatures_for(layout, issuer_name=user.get("name"),
                             issuer_position=user.get("role"))
    layout.setdefault("options", {})["doc_date"] = (layout["options"].get("doc_date")
                                                    or "26 Agustus 2026")
    pdf = pl.render_letter(layout, imgs, title=title, doc_number=number, content=content,
                           meta=meta if dl.section_visible(layout, "identitas") else None,
                           money_rows=rows if dl.section_visible(layout, "biaya") or "{{tabel_biaya}}" in content else None,
                           clauses=clauses if dl.section_visible(layout, "ketentuan") else None,
                           note=note, signatures_override=sigs)
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="pratinjau-{code}.pdf"'})
