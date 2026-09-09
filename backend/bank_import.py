"""IMPOR MUTASI REKENING (Fase 47A) — dry-run, idempoten, dan tidak pernah menelan baris.

Cacat yang ditutup modul ini: sebelum Fase 47 tidak ada satu pun jalur yang membandingkan
uang di sistem dengan uang di rekening. Penerimaan hanya bisa dicatat manual, sehingga
"sudah bayar" versi SIPRO tidak bisa dibuktikan ke bank — dan selisihnya tidak pernah
terlihat oleh siapa pun.

Aturan yang dipegang di sini (pola yang sudah terbukti pada impor biaya iklan Fase 43):

  1. **Dry-run tidak menulis apa pun.** Pemakai melihat lebih dulu apa yang akan terjadi:
     berapa baru, berapa sudah ada, berapa ditolak, dan MENGAPA baris ditolak.
  2. **Idempoten lewat kunci alami** (`fingerprint` = rekening + tanggal + arah + nominal +
     referensi/keterangan). Mengunggah berkas yang sama dua kali menghasilkan `unchanged`,
     bukan mutasi kembar — dijaga index unik di MongoDB, bukan hanya pengecekan aplikasi.
  3. **Perubahan diakui, bukan ditimpa diam-diam.** Bila keterangan/saldo berubah untuk
     kunci yang sama, barisnya di-`update` DAN perubahannya dicatat di `history`.
  4. **Baris cacat DITOLAK dengan alasan** (tanggal tidak sah, nominal nol/negatif, tidak
     ada keterangan). Tidak ada baris yang hilang tanpa jejak, karena baris hilang pada
     rekonsiliasi bank = selisih yang tidak bisa dijelaskan.
  5. **Format angka Indonesia dimengerti**: `1.500.000,00` dan `1,500,000.00` sama-sama
     dibaca 1500000 (rupiah bulat, tanpa sen).

Arah mutasi mengikuti kacamata REKENING KITA: kolom **Debit** = saldo berkurang (uang
keluar), kolom **Kredit** = saldo bertambah (uang masuk). Itu kebalikan dari sudut pandang
jurnal, jadi ditulis eksplisit di sini supaya tidak ada yang menebak.
"""
import csv
import hashlib
import io
import logging
import re

from core_utils import new_id, now_iso
from db import ORG_ID, db

logger = logging.getLogger("sipro.bank.import")

# alias kolom (huruf kecil, tanpa spasi ganda) -> makna
HEADERS = {
    "date": ("tanggal", "tgl", "date", "tanggal transaksi", "trx date", "posting date"),
    "description": ("keterangan", "uraian", "deskripsi", "description", "berita", "remark",
                    "remarks"),
    "ref": ("referensi", "ref", "no ref", "no referensi", "nomor referensi", "reference",
            "kode transaksi", "trace"),
    "debit": ("debit", "debet", "debit (idr)", "keluar", "pengurangan"),
    "credit": ("kredit", "credit", "kredit (idr)", "masuk", "penambahan"),
    "amount": ("nominal", "jumlah", "amount", "mutasi", "nilai"),
    "direction": ("arah", "direction", "tipe", "type", "jenis"),
    "balance": ("saldo", "balance", "saldo akhir", "running balance"),
}
IN_WORDS = ("in", "masuk", "kredit", "credit", "cr", "c", "debit rekening lawan")
OUT_WORDS = ("out", "keluar", "debit", "debet", "db", "d")


def _norm_header(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _map_headers(fieldnames: list) -> dict:
    """{makna: nama kolom asli} — kolom yang tidak dikenal diabaikan, bukan bikin gagal."""
    out = {}
    for raw in fieldnames or []:
        key = _norm_header(raw)
        for meaning, aliases in HEADERS.items():
            if key in aliases and meaning not in out:
                out[meaning] = raw
    return out


def parse_money(value) -> int:
    """'1.500.000,00' / '1,500,000.00' / '1500000' -> 1500000. None bila tidak bisa dibaca."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return 0
    neg = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    text = re.sub(r"[^0-9.,]", "", text)
    if not text:
        return None
    if "." in text and "," in text:
        # pemisah desimal = yang muncul TERAKHIR
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        # ',' dengan 1-2 digit di belakang = desimal; selain itu pemisah ribuan
        text = (text.replace(",", ".") if re.search(r",\d{1,2}$", text)
                else text.replace(",", ""))
    elif re.search(r"\.\d{3}(\.|$)", text):
        text = text.replace(".", "")
    try:
        amount = int(round(float(text)))
    except ValueError:
        return None
    return -amount if neg else amount


def parse_date(value) -> str:
    """ISO `YYYY-MM-DD` dari beberapa format umum ekspor bank. None bila tidak sah."""
    text = str(value or "").strip()[:19]
    if not text:
        return None
    text = text.replace("T", " ").split(" ")[0]
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", text)
    if m:
        y, mo, d = m.groups()
    else:
        m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$", text)
        if not m:
            return None
        d, mo, y = m.groups()
        if len(y) == 2:
            y = "20" + y
    try:
        from datetime import date as _date
        return _date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return None


def fingerprint(account_id: str, row: dict) -> str:
    """Kunci alami satu mutasi. Referensi dipakai bila ada; bila tidak, keterangan."""
    key = "|".join([
        str(account_id), row["date"], row["direction"], str(row["amount"]),
        (row.get("ref") or re.sub(r"\s+", " ", str(row.get("description") or "")).lower())[:120],
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()  # noqa: S324 — kunci, bukan sandi


def parse_csv(csv_text: str) -> dict:
    """Baca CSV mentah -> {rows, rejected, headers}. TIDAK menyentuh database."""
    text = csv_text.lstrip("\ufeff")
    sample = text[:4000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    cols = _map_headers(reader.fieldnames or [])
    rows, rejected = [], []
    if "date" not in cols:
        return {"rows": [], "rejected": [{
            "line": 1, "error": ("Kolom tanggal tidak ditemukan. Kolom yang dikenali: "
                                 + ", ".join(sorted(HEADERS["date"])) + ".")}],
            "headers": reader.fieldnames or []}
    for i, raw in enumerate(reader, start=2):
        def cell(meaning):
            return raw.get(cols.get(meaning) or "", "")
        date = parse_date(cell("date"))
        desc = re.sub(r"\s+", " ", str(cell("description") or "").strip())
        debit = parse_money(cell("debit")) if "debit" in cols else None
        credit = parse_money(cell("credit")) if "credit" in cols else None
        amount = parse_money(cell("amount")) if "amount" in cols else None
        direction = str(cell("direction") or "").strip().lower()
        balance = parse_money(cell("balance")) if "balance" in cols else None
        if not date:
            rejected.append({"line": i, "error": "Tanggal tidak sah/kosong.", "raw": raw})
            continue
        if not desc:
            rejected.append({"line": i, "error": "Keterangan wajib ada (dipakai mencocokkan).",
                             "raw": raw})
            continue
        if credit:
            dirn, value = "in", credit
        elif debit:
            dirn, value = "out", debit
        elif amount is not None and amount != 0:
            if direction in IN_WORDS or amount > 0 and direction not in OUT_WORDS:
                dirn = "in" if (direction in IN_WORDS or amount > 0) else "out"
            else:
                dirn = "out"
            value = abs(amount)
        else:
            rejected.append({"line": i, "error": ("Nominal tidak ditemukan/nol — isi kolom "
                                                  "Debit/Kredit atau Nominal."), "raw": raw})
            continue
        if value is None or value <= 0:
            rejected.append({"line": i, "error": "Nominal harus lebih besar dari nol.",
                             "raw": raw})
            continue
        rows.append({"line": i, "date": date, "description": desc,
                     "ref": (str(cell("ref") or "").strip() or None),
                     "direction": dirn, "amount": int(value),
                     # saldo tidak wajib: bila bank tidak mengirimnya, JANGAN tulis 0 —
                     # "saldo belum dicatat" adalah informasi, 0 adalah kebohongan.
                     "balance": (int(balance) if balance not in (None, 0) else None)})
    return {"rows": rows, "rejected": rejected, "headers": reader.fieldnames or []}


async def account_or_error(org: str, account_id: str) -> dict:
    acc = await db.bank_accounts.find_one({"id": account_id, "org_id": org}, {"_id": 0})
    if not acc:
        raise ValueError("Rekening bank tidak ditemukan.")
    return acc


async def import_csv(org: str, account_id: str, filename: str, csv_text: str, actor: str,
                     dry_run: bool = True) -> dict:
    """Impor satu berkas mutasi. `dry_run=True` HANYA melaporkan, tanpa menulis apa pun."""
    acc = await account_or_error(org, account_id)
    parsed = parse_csv(csv_text)
    ts = now_iso()
    file_sha = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    counts = {"new": 0, "updated": 0, "unchanged": 0, "rejected": len(parsed["rejected"])}
    preview, seen = [], set()
    for row in parsed["rows"]:
        fp = fingerprint(account_id, row)
        if fp in seen:
            counts["unchanged"] += 1
            preview.append({**row, "state": "unchanged", "fingerprint": fp,
                            "note": "baris kembar di dalam berkas yang sama"})
            continue
        seen.add(fp)
        existing = await db.bank_transactions.find_one(
            {"org_id": org, "fingerprint": fp}, {"_id": 0})
        if not existing:
            counts["new"] += 1
            preview.append({**row, "state": "new", "fingerprint": fp})
            if not dry_run:
                await db.bank_transactions.insert_one({
                    "id": new_id(), "org_id": org, "account_id": account_id,
                    "account_name": acc.get("name"), "fingerprint": fp,
                    "date": row["date"], "description": row["description"],
                    "ref": row["ref"], "direction": row["direction"],
                    "amount": row["amount"], "balance": row["balance"],
                    "match_state": "unmatched", "match_id": None, "match_kind": None,
                    "matched_at": None, "matched_by": None, "ignore_reason": None,
                    "source_files": [filename], "history": [],
                    "created_at": ts, "created_by": actor, "updated_at": ts})
            continue
        changed = {k: row[k] for k in ("description", "balance")
                   if row[k] is not None and row[k] != existing.get(k)}
        if changed:
            counts["updated"] += 1
            preview.append({**row, "state": "updated", "fingerprint": fp,
                            "changes": sorted(changed)})
            if not dry_run:
                await db.bank_transactions.update_one({"id": existing["id"]}, {
                    "$set": {**changed, "updated_at": ts},
                    "$addToSet": {"source_files": filename},
                    "$push": {"history": {"at": ts, "by": actor, "file": filename,
                                          "before": {k: existing.get(k) for k in changed},
                                          "after": changed}}})
        else:
            counts["unchanged"] += 1
            preview.append({**row, "state": "unchanged", "fingerprint": fp})
    statement = None
    if not dry_run:
        statement = {
            "id": new_id(), "org_id": org, "account_id": account_id,
            "account_name": acc.get("name"), "filename": filename, "sha256": file_sha,
            "rows_total": len(parsed["rows"]), "counts": counts,
            "period_from": min([r["date"] for r in parsed["rows"]], default=None),
            "period_to": max([r["date"] for r in parsed["rows"]], default=None),
            "imported_by": actor, "created_at": ts}
        await db.bank_statements.insert_one(dict(statement))
        statement.pop("_id", None)
        logger.info("Impor mutasi bank %s: %s", filename, counts)
    return {"dry_run": dry_run, "counts": counts, "rows": preview,
            "rejected": parsed["rejected"], "headers": parsed["headers"],
            "statement": statement, "account": acc, "sha256": file_sha,
            "message": ("Pratinjau saja — belum ada yang ditulis." if dry_run else
                        f"{counts['new']} mutasi baru, {counts['updated']} diperbarui, "
                        f"{counts['unchanged']} sudah ada, {counts['rejected']} ditolak.")}
