"""GENERATOR DOKUMEN OWNER (Fase 53E) — SPR 3 varian + SPKT, siap dicetak.

## Cacat NYATA yang ditutup berkas ini

Pemilik produk bertanya: *"bagaimana dokumen-dokumen yang otomatis terbuat dari data yang
sebelumnya saya berikan? bagaimana saya bisa mencetaknya?"* — dan jawaban jujurnya sebelum
Fase 53 adalah: **dokumen itu belum pernah ada di sistem**. `document_templates` hanya berisi
tiga teks pendek karangan seed (`SPR`, `PPJB`, `AJB`, masing-masing ±10 baris), sementara
empat dokumen asli owner di `docs/source_templates/` (SPR Cash Keras, SPR Cash Bertahap,
SPR KPR, SPKT) beserta seluruh klausanya — booking fee hangus 7 hari, refund 100%/50%,
potongan pembatalan 35%/50%, cicilan tanggal 7 toleransi tanggal 20, tunggak 2 bulan, SHGB
±6 bulan — tidak pernah diterjemahkan menjadi template. Layar Dokumen pun hanya bisa
membuat satu jenis: `template_code: "SPR"` yang DIKERASKAN di dua berkas frontend.

## Aturan berkas ini

1. **Template adalah DATA, bukan kode** (Dok 27 §7): tersimpan di `document_templates`
   dengan `version`, sehingga admin bisa memperbaiki kalimat tanpa deploy, dan dokumen
   menyimpan versi template yang dipakainya.
2. **Satu sumber angka** (Dok 27 §5.1): setiap rupiah dirender dari
   `contracts_engine.build_breakdown()` / rencana bayar. Tidak ada perhitungan kedua di
   lapisan template — kalau ada, dokumen dan tagihan akan berbeda.
3. **Klausa dari Pusat Konfigurasi**, bukan teks mati: 7 hari, 100%, 50%, 35%, tanggal 7/20,
   2 bulan, 6 bulan semuanya dibaca dari `[CFG]`. Mengubah kebijakan = mengubah dokumen.
4. **Angka yang belum diketahui ditulis apa adanya** ("belum ditetapkan"), TIDAK pernah
   Rp 0. Dokumen legal yang menulis "BPHTB Rp 0" adalah dokumen yang berbohong.
5. **Nomor mengikuti format owner**: `5201/SPR-CASH/HL5/VIII/2026` =
   `{urut}/{kode dokumen}/{kode proyek}/{bulan romawi}/{tahun}`.
"""
import hashlib
import logging

import contracts_engine as ce
import reference as ref
import sequences as seq
import settings_store as cfg
from core_utils import new_id, now_iso
from db import ORG_ID, ORG_NAME, db

logger = logging.getLogger("sipro.docgen")

ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
BELUM = "belum ditetapkan"

# kode template -> (nama, skema yang cocok, kode nomor dokumen, berkas asli owner)
TEMPLATES = {
    "SPR_CASH": ("Surat Pesanan Rumah — Cash Keras", "cash_keras", "SPR-CASH",
                 "SPR_CASH_HARMONY_LAND_5.docx"),
    "SPR_CASH_STAGED": ("Surat Pesanan Rumah — Cash Bertahap", "cash_bertahap", "SPR-CASHB",
                        "SPR_CASH_BERTAHAP_HARMONY_LAND_5.docx"),
    "SPR_KPR": ("Surat Pesanan Rumah — KPR", "kpr", "SPR-KPR",
                "SPR_KPR_HARMONY_LAND_5.docx"),
    "SPKT": ("Surat Pernyataan Kelebihan Tanah", None, "SPKT",
             "SPKT_HARMONY_LAND_5.docx"),
}
SPR_CODES = ("SPR_CASH", "SPR_CASH_STAGED", "SPR_KPR")


def _rp(v) -> str:
    if v is None:
        return BELUM
    return f"Rp {int(v):,}".replace(",", ".")


def _pct(v) -> str:
    return f"{float(v):g}%"


# ============================================================ isi template (data)
_HEAD_SPR = """SURAT PESANAN RUMAH
Nomor: {{doc_number}}

{{intro}}

Nama : {{customer_name}}
No. Telepon : {{customer_phone}}
Nama Properti : {{property_name}}
Alamat : {{property_address}}
Blok : {{unit_block}}
Luas Bangunan : {{building_area}}
Luas Tanah : {{land_area}}
Harga Jual : {{selling_price}}
{{dp_line}}

1. Transaksi Jual Beli
Objek transaksi adalah rumah {{unit_type_label}} yang berlokasi di {{property_name}}, Blok {{unit_block}}.
Pihak pertama, {{developer_name}}, menjual unit tersebut kepada pihak kedua, {{customer_name}}.

2. Rincian Harga & Biaya
Harga unit {{unit_type_label}} : {{selling_price}}
Booking fee : {{booking_fee}}
{{addon_rows}}{{cost_rows}}Sub Total : {{subtotal}}
Promo / potongan all-in : {{promo_discount}}
{{discount_rows}}Total : {{total}}
{{total_note}}
Catatan: biaya all-in hanya berlaku untuk biaya yang tercantum di atas. Biaya tambahan yang timbul karena permintaan khusus konsumen, perubahan data kepemilikan, perubahan skema transaksi, atau perubahan ketentuan yang disebabkan konsumen menjadi tanggung jawab konsumen.

3. Skema Pembayaran
{{payment_terms}}
"""

_CLAUSE_KEY_HANDOVER = """Serah terima kunci hanya dapat dilaksanakan setelah seluruh kewajiban pembayaran Pihak Kedua dipenuhi, diterima, dan dikonfirmasi oleh bagian Keuangan {{developer_name}}. Pelaksanaan serah terima kunci dibuktikan dengan penandatanganan Berita Acara Serah Terima (BAST) oleh kedua belah pihak.
"""

_CLAUSE_TAIL = """4. Akta Jual Beli
{{ajb_clause}}

5. Penyerahan Sertifikat
Sertifikat Hak Guna Bangunan (SHGB) akan diserahkan oleh {{developer_name}} kepada Pihak Kedua dalam jangka waktu kurang lebih {{shgb_months}} bulan sejak tanggal penandatanganan Akta Jual Beli dan/atau pengikatan jual beli di hadapan notaris, dengan ketentuan seluruh kewajiban Pihak Kedua telah dipenuhi.

6. Masa Retensi
Masa retensi terhadap bangunan mulai dilaksanakan setelah proses akad atau penandatanganan Akta Jual Beli selesai, sesuai ketentuan yang berlaku di {{developer_name}}. Masa retensi: {{retention_months}} bulan.

7. Ketentuan Pembatalan
a. Pembatalan sebelum pembangunan dimulai dikenakan potongan sebesar {{cut_before_build}} dari total pembayaran yang telah diterima Pihak Pertama.
b. Pembatalan pada saat pembangunan telah berlangsung dikenakan potongan sebesar {{cut_during_build}} dari total pembayaran yang telah diterima Pihak Pertama.
c. Pengembalian dana kepada Pihak Kedua, setelah dikurangi potongan pada poin a atau b, {{refund_clause}}

8. Penyelesaian Perselisihan
Apabila timbul perselisihan akibat pelaksanaan perjanjian ini, kedua belah pihak sepakat menyelesaikannya terlebih dahulu secara musyawarah untuk mencapai mufakat.

Demikian surat pesanan ini dibuat berdasarkan persetujuan atas ketentuan dan syarat yang telah dijelaskan sebelumnya. Dengan ini kami menyatakan telah memahami dan menyetujui seluruh poin di atas.

{{city}}, {{document_date}}
Mengetahui,
Marketing : {{marketing_name}}
Konsumen : {{customer_name}}
"""

_BOOKING_CLAUSES_KPR = """4. Ketentuan Booking Fee & BI Checking
Booking fee sebesar {{booking_fee}} dibayarkan pada saat melakukan keep unit.
Apabila hasil BI Checking tidak sesuai kriteria calon nasabah KPR, booking fee dikembalikan {{refund_bi_fail}}.
Apabila dalam waktu {{forfeit_days}} hari kalender sejak hasil BI Checking/SLIK dinyatakan memenuhi persyaratan tidak terdapat kejelasan dari calon pembeli mengenai pengumpulan berkas persyaratan KPR, Developer berhak membatalkan proses pembelian, memasarkan kembali unit tersebut, dan booking fee dinyatakan hangus.
Apabila pengajuan KPR ditolak oleh pihak bank, booking fee dikembalikan sebesar {{refund_kpr_rejected}}.
Apabila calon pembeli mengundurkan diri secara sepihak, booking fee dinyatakan hangus.
Biaya notaris meliputi SKMHT, PPJB, AJB, pengecekan sertifikat, dan balik nama sertifikat. Biaya perbankan meliputi provisi, administrasi bank, blokir angsuran, dan materai.
"""

_SPKT = """SURAT PERNYATAAN KELEBIHAN TANAH
Nomor: {{doc_number}}

Berdasarkan Surat Pesanan Rumah (SPR) Nomor {{spr_number_ref}}, para pihak sepakat mengatur ketentuan mengenai kelebihan tanah sebagaimana diuraikan dalam surat pernyataan ini.

Nama : {{customer_name}}
No. Telepon : {{customer_phone}}
Nama Properti : {{property_name}}
Alamat : {{property_address}}
Blok : {{unit_block}}

Dengan ini menyatakan bahwa unit yang dipesan memiliki kelebihan tanah dengan rincian sebagai berikut:
Luas Tanah Standar : {{standard_land_area}}
Estimasi Kelebihan Tanah : {{excess_land_m2}}
Harga Kelebihan Tanah (daftar) : {{excess_price_list}}
Harga Kelebihan Tanah (disepakati) : {{excess_price_agreed}}
Estimasi Total Harga Kelebihan Tanah : {{excess_total}}
Biaya BPHTB : {{bphtb}}
TOTAL : {{excess_grand_total}}

Ketentuan
Luas kelebihan tanah yang tercantum masih bersifat ESTIMASI dan akan mengikuti hasil pengukuran akhir yang dilakukan Developer dan/atau instansi berwenang.
Apabila hasil pengukuran akhir menunjukkan adanya selisih luas tanah, nilai transaksi disesuaikan berdasarkan harga kelebihan tanah yang telah disepakati sebesar {{excess_price_agreed}}.
Biaya kelebihan tanah tidak termasuk dalam program all-in dan menjadi kewajiban pembeli untuk melunasinya.
{{payoff_before_akad_clause}}

Demikian surat pernyataan ini dibuat berdasarkan persetujuan atas ketentuan dan syarat yang telah dijelaskan sebelumnya.

{{city}}, {{document_date}}
Mengetahui,
Marketing : {{marketing_name}}
Konsumen : {{customer_name}}
"""


_CLAUSE_STAGED = """4. Ketentuan Pembayaran Bertahap
Pembayaran dilakukan secara bertahap sesuai jadwal pada butir 3. Setiap cicilan wajib dibayar paling lambat pada tanggal jatuh tempo masing-masing termin; keterlambatan dinyatakan menunggak sesuai toleransi yang tercantum pada jadwal. Tunggakan yang melampaui batas memberi hak kepada {{developer_name}} untuk membatalkan transaksi secara sepihak sesuai ketentuan pembatalan.
Booking fee sebesar {{booking_fee}} diperhitungkan sebagai bagian dari pembayaran uang muka.
"""


def _renumber(text: str, start: int) -> str:
    """Geser nomor pasal `_CLAUSE_TAIL` (4..8) mulai dari `start` — untuk sisipan pasal."""
    names = ["Akta Jual Beli", "Penyerahan Sertifikat", "Masa Retensi", "Ketentuan Pembatalan",
             "Penyelesaian Perselisihan"]
    for i, n in reversed(list(enumerate(names))):
        text = text.replace(f"{4 + i}. {n}", f"{start + i}. {n}")
    return text


def template_content(code: str) -> str:
    """Isi template sebagai DATA. Disimpan ke `document_templates` (bisa diubah admin).

    Fase 88D: TIAP jenis SPR punya naskah bawaan sendiri — cash keras (pelunasan setelah
    bangun), cash bertahap (pasal cicilan), KPR (pasal booking fee & BI checking).
    """
    if code == "SPKT":
        return _SPKT
    if code == "SPR_KPR":
        return _HEAD_SPR + _CLAUSE_KEY_HANDOVER + "\n" + _BOOKING_CLAUSES_KPR + "\n" \
            + _renumber(_CLAUSE_TAIL, 5)
    if code == "SPR_CASH_STAGED":
        return _HEAD_SPR + _CLAUSE_KEY_HANDOVER + "\n" + _CLAUSE_STAGED + "\n" \
            + _renumber(_CLAUSE_TAIL, 5)
    return _HEAD_SPR + _CLAUSE_KEY_HANDOVER + "\n" + _CLAUSE_TAIL


async def ensure_templates(org: str = ORG_ID) -> dict:
    """Pasang/segarkan 4 template owner. Idempoten; `version` naik bila isinya berubah.

    Naskah yang SUDAH DISUNTING pemakai (`updated_by` terisi lewat layar Template Dokumen)
    tidak pernah ditimpa bawaan kode — dulu setiap restart mengembalikan suntingan admin.
    """
    out = {"created": [], "updated": [], "unchanged": [], "customized": []}
    ts = now_iso()
    for code, (name, scheme, doc_code, source) in TEMPLATES.items():
        content = template_content(code)
        cur = await db.document_templates.find_one({"org_id": org, "code": code}, {"_id": 0})
        if not cur:
            await db.document_templates.insert_one({
                "id": new_id(), "org_id": org, "code": code, "name": name,
                "scheme": scheme, "doc_code": doc_code, "content": content,
                "version": 1, "is_active": True, "generator": True,
                "source_file": f"docs/source_templates/{source}",
                "created_by": "system", "created_at": ts, "updated_at": ts})
            out["created"].append(code)
        elif cur.get("updated_by"):
            if cur.get("doc_code") != doc_code:
                await db.document_templates.update_one({"id": cur["id"]}, {"$set": {"doc_code": doc_code}})
            out["customized"].append(code)
        elif (cur.get("content") or "") != content or cur.get("doc_code") != doc_code:
            await db.document_templates.update_one({"id": cur["id"]}, {"$set": {
                "name": name, "scheme": scheme, "doc_code": doc_code, "content": content,
                "version": int(cur.get("version") or 1) + 1, "is_active": True,
                "generator": True, "source_file": f"docs/source_templates/{source}",
                "updated_at": ts}})
            out["updated"].append(code)
        else:
            out["unchanged"].append(code)
    return out


# ============================================================ penomoran (format owner)
async def next_doc_number(org: str, code: str, project: dict) -> str:
    """Bawaan `{urut}/{kode}/{kode proyek}/{bulan romawi}/{tahun}` — format dokumen owner.

    Pola, reset, lebar, dan cakupan urutan kini diatur di Pusat Konfigurasi › Penomoran
    (aturan `docnum`). `[CFG] docnum.*` lama dipakai sebagai bawaan bila aturan belum diubah.
    """
    import numbering
    doc_code = TEMPLATES.get(code, (None, None, code, None))[2]
    # Aturan PER JENIS (`docnum:SPR-KPR` dst.) menang; bila belum diubah → aturan keluarga
    # `docnum`; bila itu pun belum diubah → format bawaan owner ([CFG] docnum.*).
    per_type = (await numbering.effective_rule(org, f"docnum:{doc_code}")
                if f"docnum:{doc_code}" in numbering.REGISTRY_BY_KEY
                else {"overridden": False})
    rule = per_type if per_type["overridden"] else await numbering.effective_rule(org, "docnum")
    pcode = (project.get("code") or "").strip() or "UMUM"
    scope = f"docnum:{doc_code}"
    if not rule["overridden"]:
        scope_mode = str(await cfg.get("docnum.scope", org_id=org) or "per_project")
        reset = str(await cfg.get("docnum.reset_policy", org_id=org) or "yearly")
        width = int(await cfg.get("docnum.width", org_id=org) or 4)
        ts = now_iso()
        year, month = ts[:4], int(ts[5:7])
        if scope_mode in ("per_project", "per_project_month"):
            scope += f":{pcode}"
        if scope_mode == "per_project_month":
            scope += f":{month:02d}"
        period = None if reset == "never" else (year if reset == "yearly" else f"{year}{month:02d}")
        n = await seq.next_seq(scope, org, period)
        return f"{str(n).zfill(width)}/{doc_code}/{pcode}/{ROMAN[month]}/{year}"
    return await numbering.generate(scope, org, rule_key=rule["key"], context={
        "project_code": pcode, "project_name": project.get("name"), "template_code": doc_code})


# ============================================================ konteks (angka kontrak)
def split_terms(plan: dict) -> tuple:
    """(termin unit, baris add-on) — dari AR bila sudah menagih, dari skema kontrak bila belum."""
    if plan.get("state") == "ada":
        src = plan.get("terms") or []
    else:
        src = plan.get("rules_full") or []
    unit = [t for t in src if t.get("basis") != "addon" and not t.get("addon_code")]
    addon = [t for t in src if t.get("basis") == "addon" or t.get("addon_code")]
    return unit, addon


def dp_percent(unit_terms: list):
    """DP% = termin pertama yang NYATA (persen skema, atau nominal ÷ total termin unit)."""
    if not unit_terms:
        return None
    first = unit_terms[0]
    if first.get("basis", "percent") == "percent" and first.get("value") is not None:
        return round(float(first["value"]), 2)
    total = sum(int(t.get("amount") or 0) for t in unit_terms)
    if not total or first.get("amount") is None:
        return None
    return round(int(first["amount"]) / total * 100, 2)


def term_line(no: int, t: dict) -> str:
    line = f"{no}. {t.get('label')} : {_rp(t.get('amount'))}"
    if t.get("due_date"):
        line += f" — jatuh tempo {str(t.get('due_date'))[:10]}"
    if t.get("event_based") or not t.get("due_date"):
        if t.get("due_rule"):
            line += f" ({t['due_rule']})"
    elif int(t.get("grace_days") or 0):
        line += f" (toleransi {int(t['grace_days'])} hari)"
    return line


def buyer_incomplete_labels(bd: dict) -> list:
    """Komponen biaya PEMBELI yang kosong (subset `costs_incomplete_labels`, label manusia) —
    pajak penjual (PPh) bukan urusan total pembeli, jadi tidak membuat SPR "sementara"."""
    return [r["label"] for r in bd.get("rows") or []
            if r.get("group") == "biaya" and r.get("state") == "empty"
            and r.get("finance_treatment") != "tax_out"]


async def build_context(org: str, contract: dict, code: str, *, actor_name: str,
                        doc_number: str) -> dict:
    bd = await ce.build_breakdown(org, contract)
    plan = await ce.payment_plan(org, contract)
    if plan.get("state") != "ada":
        spec = await ce.scheme_terms_spec(org, contract.get("scheme"), contract)
        plan["rules_full"] = spec.get("items") or []
    unit = await db.units.find_one({"id": contract.get("unit_id")}, {"_id": 0}) or {}
    project = await db.projects.find_one({"id": contract.get("project_id")}, {"_id": 0}) or {}
    cust = await db.customers.find_one({"id": contract.get("customer_id")}, {"_id": 0}) or {}
    deal = await db.deals.find_one({"id": contract.get("deal_id")}, {"_id": 0}) or {}
    scheme = contract.get("scheme")

    def row(c):
        for r in bd["rows"]:
            if r["code"] == c:
                return r
        return {}

    def money(c):
        r = row(c)
        if r.get("state") == "not_applicable":
            return "tidak berlaku"
        return _rp(r.get("amount"))

    # ---- SATU SUMBER angka pembayaran (Jalur 1): termin dari AR yang MENAGIH (dibuat dari
    # `deal.scheme_id`); bila AR belum lahir, dari skema pembayaran kontrak itu sendiri.
    # TIDAK ADA angka dari `[CFG] payment.*` selain kalimat toleransi/tunggakan.
    unit_terms, addon_terms = split_terms(plan)
    dp_pct = dp_percent(unit_terms)
    intro = {
        "cash_keras": ("Menindaklanjuti pembelian rumah yang dilakukan secara pembayaran "
                       "tunai (cash keras) atas nama:"),
        "cash_bertahap": ("Menindaklanjuti pembelian rumah yang dilakukan secara pembayaran "
                          "tunai (cash bertahap) atas nama:"),
        "kpr": ("Menindaklanjuti pembelian rumah yang dilakukan melalui fasilitas Kredit "
                "Pemilikan Rumah (KPR) dengan data pemesanan sebagai berikut:"),
    }.get(scheme, "Menindaklanjuti pembelian rumah atas nama:")

    # Baris add-on DINAMIS (permintaan owner: spek tambahan sebagai baris tersendiri).
    addon_lines = []
    for c, label in (("ADDON_SPEC", "Spek tambahan"), ("EXCESS_LAND", "Kelebihan tanah"),
                     ("HOOK_FEE", "Biaya hook")):
        r = row(c)
        if r.get("amount"):
            for it in (r.get("meta") or {}).get("items") or []:
                addon_lines.append(f"{it.get('name') or label} : {_rp(it.get('amount'))}")
            if not (r.get("meta") or {}).get("items"):
                addon_lines.append(f"{label} : {_rp(r.get('amount'))}")
    addon_rows = ("\n".join(addon_lines) + "\n") if addon_lines else ""

    # Fase 88C: rincian potongan per aturan + SASARANNYA (harga / uang muka / booking fee /
    # komponen biaya) — pembeli membaca dari mana potongannya dikurangkan.
    disc_items = (row("PROMO_DISCOUNT").get("meta") or {}).get("items") or []
    cost_disc = [(c, int((c.get("meta") or {}).get("discount") or 0)) for c in bd["rows"]
                 if c.get("group") == "biaya" and (c.get("meta") or {}).get("discount")]
    disc_lines = [f"  - {it.get('name') or it.get('code')} (dipotong dari {it.get('target_label')}) : "
                  f"{_rp(it.get('amount'))}" for it in disc_items]
    disc_lines += [f"  - Potongan {c['label']} : {_rp(d)} (biaya setelah potongan {_rp(c.get('amount'))})"
                   for c, d in cost_disc]
    discount_rows = ("\n".join(disc_lines) + "\n") if disc_lines else ""

    kpr_rows = ""
    if scheme == "kpr":
        kpr_rows = (f"Biaya bank : {money('BANK_FEE')}\n"
                    f"Asuransi jiwa & kebakaran : {money('INSURANCE')}\n")
    # Komponen biaya DINAMIS dari snapshot skema all-in (`costs.components` → breakdown):
    # baris yang ada di Finance (invoice biaya) adalah baris yang tercetak — bukan daftar
    # tetap BPHTB/notaris yang bisa "belum ditetapkan" padahal INB sudah terbit.
    cost_rows = "".join(
        f"{r['label']} : "
        + ("tidak berlaku" if r.get("state") == "not_applicable" else _rp(r.get("amount")))
        + (" (ditanggung developer — all-in)" if r.get("finance_treatment") == "developer_borne"
           and r.get("amount") is not None else "")
        + "\n"
        for r in bd["rows"] if r.get("group") == "biaya" and r.get("state") != "not_applicable")
    # Label manusia (`costs_incomplete_labels`), dibatasi ke komponen yang ditagih ke pembeli.
    incomplete = [x for x in (bd.get("costs_incomplete_labels") or []) if x in buyer_incomplete_labels(bd)]

    # Termin: dari AR yang MENAGIH (dibuat dari `deal.scheme_id`); nomor urut milik termin
    # unit, add-on dicetak terpisah. Kalimat aturan hanya untuk termin berbasis peristiwa
    # (tanggalnya perkiraan) — termin bertanggal pasti tidak diberi kalimat "saat kontrak
    # diaktifkan" dari skema bawaan, karena tagihannya sudah berjalan sejak booking.
    if plan["state"] == "ada":
        terms = "\n".join(term_line(i + 1, t) for i, t in enumerate(unit_terms))
        if addon_terms:
            terms += "\nTagihan terpisah (add-on, tidak termasuk dasar termin/KPR):\n" + "\n".join(
                f"- {t.get('label')} : {_rp(t.get('amount'))}"
                + (f" — jatuh tempo {str(t.get('due_date'))[:10]}" if t.get("due_date") else "")
                for t in addon_terms)
    else:
        terms = "\n".join(
            f"{i + 1}. {r['label']}"
            + (f" : {_pct(r['value'])} dari harga" if r.get("basis") == "percent" else "")
            + (f" ({r.get('due_rule') or '-'})" if r.get("event") or not r.get("due_date")
               else "")
            for i, r in enumerate(unit_terms))
        terms += ("\nCatatan: nominal termin belum dibuat sistem — "
                  + (plan.get("reason") or ""))

    sisa_pct = (100 - dp_pct) if dp_pct is not None else None
    n_inst = max(0, len(unit_terms) - 1)
    arrears = int(await cfg.get("payment.staged.arrears_months_to_cancel", org_id=org) or 2)
    if scheme == "cash_bertahap" and sisa_pct is not None:
        terms += (f"\nPelunasan {sisa_pct:g}% dibayar bertahap {n_inst}× cicilan sesuai jadwal "
                  "di atas, masing-masing paling lambat pada tanggal jatuh tempo termin; "
                  "cicilan yang belum dibayar melewati toleransi terminnya dinyatakan "
                  f"MENUNGGAK. Tunggakan {arrears} bulan (berturut-turut maupun akumulatif) "
                  "memberi hak Pihak Pertama membatalkan transaksi secara sepihak dan "
                  "menjual kembali unit kepada pihak lain.")
    if scheme == "cash_keras" and sisa_pct is not None:
        days = int(await cfg.get("payment.cash.payoff_days_after_completion", org_id=org) or 30)
        g2 = int(await cfg.get("payment.cash.payoff_grace_days", org_id=org) or 7)
        terms += (f"\nPelunasan {sisa_pct:g}% wajib dilakukan setelah pembangunan "
                  f"mencapai 100%, paling lambat {days} hari kalender sejak pemberitahuan "
                  f"penyelesaian pembangunan; perpanjangan {g2} hari kalender.")

    excess_row = row("EXCESS_LAND")
    excess_items = (excess_row.get("meta") or {}).get("items") or []
    excess_qty = sum(float(i.get("qty") or 0) for i in excess_items)
    agreed = next((i.get("unit_price") for i in excess_items if i.get("unit_price")), None)
    master = await db.addon_items.find_one({"org_id": org, "category": "kelebihan_tanah"},
                                          {"_id": 0, "unit_price": 1})
    if not (master or {}).get("unit_price"):
        cfg_price = int(await cfg.get("addon.excess_land_price_per_m2", org_id=org) or 0)
        master = {"unit_price": cfg_price} if cfg_price else master
    ctx = {
        "doc_number": doc_number,
        "intro": intro,
        "customer_name": cust.get("name") or deal.get("lead_name") or BELUM,
        "customer_phone": cust.get("phone") or BELUM,
        "property_name": project.get("name") or BELUM,
        "property_address": project.get("address") or (
            "(alamat proyek belum diisi di Master Data → Proyek)"),
        "developer_name": project.get("developer_name") or ORG_NAME,
        "city": project.get("city") or "—",
        "unit_block": unit.get("code") or BELUM,
        "unit_type_label": f"tipe {unit.get('type')}" if unit.get("type") else BELUM,
        "building_area": (f"{unit.get('building_area')} m²" if unit.get("building_area")
                          else BELUM),
        "land_area": f"{unit.get('land_area')} m²" if unit.get("land_area") else BELUM,
        "selling_price": money("UNIT_PRICE"),
        "dp_line": ((f"Plafon Kredit : {money('PLAFON_KREDIT')}\n" if scheme == "kpr" else "")
                    + "Uang Muka : " + (_pct(dp_pct) if dp_pct is not None else BELUM)),
        "booking_fee": money("BOOKING_FEE"),
        "addon_rows": addon_rows,
        "cost_rows": cost_rows,
        "kpr_cost_rows": kpr_rows,
        "bphtb": money("BPHTB"),
        "notary_fee": money("NOTARY_FEE"),
        "pph_seller": money("PPH_SELLER"),
        "promo_discount": money("PROMO_DISCOUNT"),
        "discount_rows": discount_rows,
        "subtotal": _rp(bd["gross_price"] + bd["costs_total"]),
        "total": _rp(bd["total_bill"]),
        "total_note": (f"Catatan: total masih SEMENTARA — komponen "
                       f"{', '.join(incomplete)} belum diisi, "
                       "jadi angka di atas belum lengkap."
                       if incomplete else ""),
        "payment_terms": terms,
        "ajb_clause": ("Akta Jual Beli ditandatangani pada saat akad kredit di hadapan "
                       "notaris yang ditunjuk Pihak Pertama, setelah SP3K diterbitkan bank "
                       "dan seluruh biaya yang menjadi kewajiban Pihak Kedua (termasuk "
                       "kelebihan tanah, bila ada) telah dilunasi."
                       if scheme == "kpr" else
                       "Setelah Pihak Kedua melakukan pelunasan dan proses serah terima "
                       "kunci selesai, kedua belah pihak menandatangani Akta Jual Beli "
                       "dan/atau pengikatan jual beli melalui notaris yang ditunjuk Pihak "
                       "Pertama sesuai ketentuan perundang-undangan."),
        "shgb_months": str(int(await cfg.get("legal.shgb_months_after_ajb", org_id=org) or 6)),
        "retention_months": str(int(await cfg.get("retention.months", org_id=org) or 3)),
        "cut_before_build": _pct(await cfg.get("cancellation.cut_before_build_pct",
                                               org_id=org) or 35),
        "cut_during_build": _pct(await cfg.get("cancellation.cut_during_build_pct",
                                               org_id=org) or 50),
        "refund_clause": ("dilakukan setelah unit yang dibatalkan berhasil terjual kembali "
                          "kepada pihak lain dan Pihak Pertama menerima pembayaran dari "
                          "pembeli baru."
                          if await cfg.get("cancellation.refund_requires_resale", org_id=org)
                          else "dilakukan sesuai jadwal pengembalian dana Pihak Pertama."),
        "refund_bi_fail": _pct(await cfg.get("booking_fee.refund_bi_fail_pct",
                                             org_id=org) or 100),
        "refund_kpr_rejected": _pct(await cfg.get("booking_fee.refund_kpr_rejected_pct",
                                                  org_id=org) or 50),
        "forfeit_days": str(int(await cfg.get("booking_fee.forfeit_no_clarity_days",
                                              org_id=org) or 7)),
        "document_date": now_iso()[:10],
        "marketing_name": actor_name or "—",
        # ---- khusus SPKT
        "spr_number_ref": await _spr_number_ref(org, contract),
        "standard_land_area": (f"{unit.get('land_area')} m²" if unit.get("land_area")
                               else BELUM),
        "excess_land_m2": f"{excess_qty:g} m² (estimasi)" if excess_qty else BELUM,
        "excess_price_list": _rp((master or {}).get("unit_price")) + " / m²"
        if master else BELUM,
        "excess_price_agreed": (_rp(agreed) + " / m²") if agreed else BELUM,
        "excess_total": _rp(excess_row.get("amount")),
        "excess_grand_total": _rp((excess_row.get("amount") or 0)
                                  + int(row("BPHTB").get("amount") or 0))
        if excess_row.get("amount") is not None else BELUM,
        "payoff_before_akad_clause": (
            "Pelunasan biaya kelebihan tanah wajib diselesaikan SEBELUM proses akad kredit "
            "dilaksanakan."
            if await cfg.get("addon.excess_land_must_be_paid_before_akad", org_id=org)
            else "Pelunasan biaya kelebihan tanah mengikuti jadwal termin kontrak."),
    }
    return ctx


async def _spr_number_ref(org: str, contract: dict) -> str:
    d = await db.documents.find_one(
        {"org_id": org, "deal_id": contract["deal_id"],
         "template_code": {"$in": list(SPR_CODES)}},
        {"_id": 0, "doc_number": 1}, sort=[("created_at", -1)])
    return (d or {}).get("doc_number") or "(SPR belum diterbitkan)"


def render(content: str, ctx: dict) -> str:
    """Ganti `{{key}}`. Placeholder yang tidak dikenal DIBIARKAN terlihat, bukan dihapus.

    Kenapa dibiarkan: placeholder yang hilang tanpa jejak membuat dokumen tampak lengkap
    padahal ada bagian yang tidak terisi. Lebih baik terlihat mencolok saat pratinjau.
    """
    from document_richtext import substitute
    return substitute(content, ctx, missing=lambda key: f"[{key} TIDAK TERISI]")


# ============================================================ validasi pra-generate
def layout_amounts(bd: dict) -> dict:
    """Nominal kontrak → kode baris `doc_layout.MONEY_ROWS` (nilai milik mesin, bukan konfigurasi)."""
    by = {r["code"]: r for r in bd.get("rows") or []}
    amt = lambda c: (by.get(c) or {}).get("amount")  # noqa: E731
    opt = lambda c: amt(c) if c in by else 0  # noqa: E731 — komponen opsional yang tidak ada = 0
    out = {"PRICE_LIST": bd.get("gross_price"), "DISCOUNT": bd.get("promo_discount"),
           "PRICE_DEAL": bd.get("nett_price"), "BOOKING_FEE": bd.get("booking_fee"),
           "DP": opt("DP"), "ADDON_SPEC": opt("ADDON_SPEC"), "EXCESS_LAND": opt("EXCESS_LAND"),
           "HOOK_FEE": opt("HOOK_FEE"), "BPHTB": amt("BPHTB"), "BANK_FEE": amt("BANK_FEE"),
           "INSURANCE": amt("INSURANCE"), "NOTARY": amt("NOTARY_FEE"),
           "TOTAL": bd.get("total_bill")}
    # Komponen skema all-in di luar daftar standar ikut tercetak dengan kodenya sendiri.
    for r in bd.get("rows") or []:
        if r.get("group") == "biaya" and r["code"] not in out and r["code"] != "NOTARY_FEE" \
                and r.get("state") != "not_applicable":
            out[r["code"]] = r.get("amount")
    return out


async def _spr_gates(org: str, contract: dict) -> list:
    """Gerbang SPR dari Pusat Konfigurasi (dulu kunci-kunci ini tidak pernah dibaca kode)."""
    blocks = []
    deal = await db.deals.find_one({"id": contract.get("deal_id")}, {"_id": 0}) or {}
    # Varian SPR ditentukan JENIS skema yang dipilih sales pada deal — kontrak yang jenisnya
    # berbeda (tebakan lama / diubah manual) tidak boleh mencetak SPR sampai disamakan.
    if deal.get("scheme_id"):
        sch = await db.payment_schemes.find_one({"id": deal["scheme_id"]}, {"_id": 0, "kind": 1})
        kind = (sch or {}).get("kind")
        if kind and kind != contract.get("scheme"):
            blocks.append(("skema_deal_beda",
                           f"Skema pembayaran deal adalah {ref.label_of('payment_scheme', kind)}, "
                           f"sedangkan kontrak berjenis {contract.get('scheme_label')}. "
                           "Samakan jenis skema kontrak dengan deal sebelum menerbitkan SPR."))
    if await cfg.get("reservation.require_booking_fee_before_spr", org_id=org):
        if deal.get("booking_fee_status") not in ("recorded", "verified"):
            blocks.append(("booking_fee_belum",
                           "Booking fee belum tercatat/terverifikasi — konfigurasi "
                           "`Booking fee wajib sebelum SPR` menyala."))
    # Gerbang SLIK PER JENIS SKEMA (`[CFG] slik.scheme_kinds`, bawaan hanya KPR): pembeli
    # tunai tidak mengajukan kredit — dulu SPR Cash Bertahap tertahan "SLIK belum lolos".
    slik_kinds = list(await cfg.get("slik.scheme_kinds", org_id=org) or [])
    if (str(await cfg.get("slik.gate", org_id=org) or "before_spr") == "before_spr"
            and contract.get("scheme") in slik_kinds):
        lead = await db.leads.find_one({"id": contract.get("lead_id")},
                                       {"_id": 0, "slik": 1}) or {}
        if (lead.get("slik") or {}).get("status") not in ("clear", "flagged"):
            blocks.append(("slik_belum", "Pra-skrining BI/SLIK belum lolos (konfigurasi "
                                         "`Kapan SLIK diwajibkan` = sebelum SPR)."))
    required = list(await cfg.get("lead.required_demography", org_id=org) or [])
    if required:
        cust = await db.customers.find_one({"id": contract.get("customer_id")},
                                           {"_id": 0}) or {}
        kosong = [f for f in required if not cust.get(f)]
        if kosong:
            blocks.append(("demografi_belum_lengkap",
                           "Data pembeli wajib belum lengkap: " + ", ".join(kosong) + "."))
    return blocks


async def applicable(org: str, contract: dict) -> list:
    """Daftar template + boleh/tidak diterbitkan + sebabnya (dipakai layar & API)."""
    bd = await ce.build_breakdown(org, contract)
    spr_gates = await _spr_gates(org, contract)
    kurang = buyer_incomplete_labels(bd)
    out = []
    for code, (name, scheme, _dc, _src) in TEMPLATES.items():
        blocks = []
        if code in SPR_CODES:
            blocks.extend(spr_gates)
        if scheme and contract.get("scheme") != scheme:
            blocks.append(("skema_tidak_cocok",
                           f"Template ini untuk skema "
                           f"{ref.label_of('payment_scheme', scheme)}, sedangkan kontrak "
                           f"ini {contract.get('scheme_label')}."))
        if code == "SPKT" and not bd.get("has_excess_land"):
            blocks.append(("tanpa_kelebihan_tanah",
                           "Tidak ada add-on kelebihan tanah pada kontrak ini."))
        if code == "SPR_KPR" and bd.get("plafon_kredit") is None:
            blocks.append(("plafon_belum_ada",
                           "Plafon KPR belum diisi pada komponen biaya kontrak."))
        if not int(bd.get("gross_price") or 0):
            blocks.append(("harga_nol", "Harga unit masih nol — periksa master unit."))
        existing = await db.documents.count_documents(
            {"org_id": org, "deal_id": contract["deal_id"], "template_code": code})
        out.append({
            "code": code, "name": name, "scheme": scheme,
            "can_generate": not blocks,
            "blocks": [{"code": c, "label": ref.label_of("docgen_block", c), "detail": d}
                       for c, d in blocks],
            "existing": existing,
            "warnings": ([("Komponen biaya belum lengkap ("
                           + ", ".join(x for x in (bd.get("costs_incomplete_labels") or [])
                                       if x in kurang)
                           + ") — dokumen akan menulis 'belum ditetapkan', bukan Rp 0.")]
                         if kurang and code != "SPKT" else []),
        })
    return out


async def generate(org: str, contract: dict, code: str, actor: dict,
                   note: str = None) -> dict:
    """Terbitkan dokumen (draft) dari template owner. Angka murni dari kontrak."""
    tpl = await db.document_templates.find_one({"org_id": org, "code": code}, {"_id": 0})
    if not tpl:
        await ensure_templates(org)
        tpl = await db.document_templates.find_one({"org_id": org, "code": code}, {"_id": 0})
    if not tpl:
        raise ValueError(f"Template {code} tidak ada di master dokumen.")
    apps = {a["code"]: a for a in await applicable(org, contract)}
    info = apps.get(code)
    if info and not info["can_generate"]:
        raise ValueError("Dokumen belum bisa diterbitkan. "
                         + " ".join(b["detail"] for b in info["blocks"]))
    project = await db.projects.find_one({"id": contract.get("project_id")}, {"_id": 0}) or {}
    number = await next_doc_number(org, code, project)
    ctx = await build_context(org, contract, code, actor_name=actor.get("name"),
                              doc_number=number)
    content = render(tpl["content"], ctx)
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "template_id": tpl["id"], "template_code": code,
        "template_version": int(tpl.get("version") or 1),
        "doc_number": number, "title": tpl.get("name") or code,
        "deal_id": contract["deal_id"], "contract_id": contract["id"],
        "lead_id": contract.get("lead_id"), "customer_id": contract.get("customer_id"),
        "unit_id": contract.get("unit_id"), "assigned_to": contract.get("assigned_to"),
        "content": content, "status": "draft", "signatures": [],
        "context_snapshot": {k: v for k, v in ctx.items() if k != "payment_terms"},
        "amounts_snapshot": await _amounts_snapshot(org, contract),
        "note": note, "warnings": (info or {}).get("warnings") or [],
        "created_by": actor.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.documents.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


async def _amounts_snapshot(org: str, contract: dict) -> dict:
    """Angka numerik SPR saat terbit — dibandingkan Finance sebelum tanda tangan (spr_compare)."""
    import spr_compare
    return await spr_compare.spr_amounts(org, contract)
