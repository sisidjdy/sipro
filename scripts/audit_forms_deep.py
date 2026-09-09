#!/usr/bin/env python3
"""audit_forms_deep.py — audit MENDALAM cacat form frontend (pelengkap forensic_audit).

Berbeda dari `forensic_audit.audit_forms` (mencocokkan NAMA field terhadap REF_HINTS),
skrip ini membaca setiap elemen `<Input>` BESERTA label yang benar-benar MILIKNYA, lalu
menilai dari bahasa label apakah field itu semestinya:

  E1  dropdown (enum/relasi)    -> label seperti "status", "tipe", "kategori", "bank", ...
  E2  input angka (type=number) -> label uang/jumlah (harga, nilai, plafon, bobot, persen, qty)
  E3  input tanggal (type=date) -> label tanggal/jatuh tempo/tenggat
  E4  tanpa label & placeholder & aria-label (tidak jelas bagi pengguna & tidak bisa diuji)
  E5  peta label enum HARDCODE di frontend padahal grup-nya ada di SSOT `/api/reference`
  E6  opsi <SelectItem> enum HARDCODE di dalam <SelectContent> padahal grup-nya ada di SSOT

Fase 26 — atribusi label diperbaiki: label diambil dari `</Label>` TERDEKAT SEBELUM elemen,
dan dibatalkan bila di antaranya masih ada elemen input lain (dulu memakai jendela ±3 baris
sehingga label field lain terbaca -> 5 dari 7 temuan E2/E3 adalah false positive).

Keluar 0 bila tidak ada temuan E1/E5/E6 (blocking); E2/E3/E4 dilaporkan sebagai peringatan.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")
import reference as ref  # noqa: E402  (SSOT: dipakai untuk mendeteksi vocabulary hardcode)

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend" / "src"
SKIP_DIRS = {"ui", "node_modules"}
INPUT_LIKE = re.compile(r"<(Input|Select|Textarea|ReferenceSelect|Checkbox|SelectTrigger)\b")

ENUM_WORDS = [
    "status", "tipe", "jenis", "kategori", "satuan", "metode", "cara bayar", "prioritas",
    "akun", "proyek", "unit", "lead", "pelanggan", "customer", "vendor", "subkon",
    "subkontraktor", "instansi", "cuaca", "bidang", "template", "skema", "peran", "role",
    "bank", "channel", "kanal", "sumber", "tahap", "severity", "keparahan", "basis",
    "pemicu", "trigger", "pic", "penanggung jawab", "ditugaskan", "assign",
]
NUMBER_WORDS = [
    "harga", "nilai", "jumlah", "total", "biaya", "fee", "plafon", "dp ", "dp(", "uang muka",
    "bobot", "persen", "%", "tenor", "qty", "kuantitas", "volume", "denda", "rp", "angsuran",
    "retensi", "diskon", "luas", "progres", "progress",
]
DATE_WORDS = ["tanggal", "jatuh tempo", "deadline", "tenggat", "tgl"]
FREE_TEXT_HINT = [
    "nama", "keterangan", "catatan", "alamat", "email", "telepon", "no.", "nomor", "kode",
    "notaris", "ntpn", "nik", "npwp", "judul", "memo", "deskripsi", "cari", "pencarian",
    "url", "token", "sandi", "password", "pesan", "isi", "link", "referensi", "id ",
    "milestone", "periode", "label", "peralatan", "material",
]
# Pengecualian sah & terverifikasi.
ALLOW_E1 = {("BoQPage.js", "kode biaya"), ("BoQPage.js", "cost_code"),
            # Fase 63 — "Lead / pembeli" pada AgendaFormDialog BUKAN teks bebas: kotak ini
            # adalah PENCARIAN relasi (hasilnya dipilih dari daftar, nilai yang tersimpan
            # selalu `lead_id`). Dropdown sungguhan tidak dipakai karena jumlah lead bisa
            # ribuan — memuat semuanya ke satu <Select> justru membuat layar tidak terpakai.
            ("AgendaFormDialog.js", "lead / pembeli")}
# StatusPill menyimpan peta fallback SECARA SENGAJA: dipakai portal pembeli yang tidak
# memuat sesi staf (tidak ada akses /api/reference). Didokumentasikan di file itu.
ALLOW_E5_FILES = {"patterns/StatusPill.js"}

findings = {"E1": [], "E2": [], "E3": [], "E4": [], "E5": [], "E6": []}


def has_word(low: str, words) -> bool:
    """Cocokkan kata kunci pada BATAS KATA, bukan substring.

    Fase 27 — presisi tahap kedua: pencocokan substring membuat label yang sah
    dianggap cacat, mis. label "Tanggal perolehan" terdeteksi E1 karena mengandung
    'role' (pe-ROLE-han), dan "Nilai residu" bisa tertangkap kata lain. Pola ini tetap
    menangkap frasa multi-kata ("cara bayar", "penanggung jawab") dan simbol ("%").
    """
    for w in words:
        if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low):
            return True
    return False


def own_label(src: str, pos: int) -> str:
    """Label yang BENAR-BENAR milik elemen pada posisi `pos` (atau placeholder/aria-label)."""
    close = src.rfind("</Label>", 0, pos)
    if close != -1 and not INPUT_LIKE.search(src[close:pos]):
        open_tag = src.rfind("<Label", 0, close)
        if open_tag != -1:
            inner = src[open_tag:close]
            text = re.sub(r"<[^>]*>", "", inner[inner.find(">") + 1:]) if ">" in inner else ""
            text = re.sub(r"\{[^}]*\}", "", text).strip()
            if 2 <= len(text) <= 60:
                return text
    el = element_text(src, pos)
    m = re.search(r'placeholder=["\']([^"\']{2,60})["\']', el)
    if m:
        return m.group(1).strip()
    m = re.search(r'aria-label=\{?["\']([^"\']{2,60})["\']', el)
    if m:
        return m.group(1).strip()
    # aria-label={ekspresi JS} (mis. template string / variabel) tetap dianggap berlabel
    m = re.search(r"aria-label=\{([^}]{2,80})\}", el)
    if m:
        return re.sub(r"[`${}]", "", m.group(1)).strip() or "aria-label"
    return ""


def element_text(src: str, pos: int) -> str:
    chunk = src[pos:pos + 600]
    end = chunk.find("/>")
    return chunk[:end + 2] if end != -1 else chunk


def line_of(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def audit_inputs(rel: str, src: str):
    for m in re.finditer(r"<Input\b", src):
        pos = m.start()
        el = element_text(src, pos)
        label = own_label(src, pos)
        low = label.lower()
        # `[\w-]+` bukan `\w+`: tipe HTML bertanda hubung (`datetime-local`) dulu tidak
        # terbaca sehingga jatuh ke default "text" — tiga field yang SUDAH memakai
        # pemilih tanggal dilaporkan sebagai cacat E3 (false positive).
        typ = re.search(r'type=["\']([\w-]+)["\']', el)
        typ = typ.group(1) if typ else "text"
        ln = line_of(src, pos)
        if not label:
            findings["E4"].append(f"{rel}:{ln} <Input> tanpa label/placeholder/aria-label")
            continue
        if (Path(rel).name, low) in ALLOW_E1:
            continue
        free_text = has_word(low, FREE_TEXT_HINT)
        numeric = typ == "number" or has_word(low, NUMBER_WORDS)
        # Presisi E1: input BERTIPE tanggal tidak mungkin jadi dropdown enum. Tanpa penyaring
        # ini, penyaring rentang tanggal yang labelnya memuat kata objek ("Lead dari",
        # "Proyek sejak") dituduh "harus dropdown" — cacat palsu yang memaksa label dibuat
        # kabur hanya demi menyenangkan gate.
        date_typed = typ in ("date", "datetime-local", "month", "time", "week")
        if has_word(low, ENUM_WORDS) and not free_text and not numeric and not date_typed:
            findings["E1"].append(f"{rel}:{ln} label '{label}' -> harus dropdown (enum/relasi)")
        if has_word(low, NUMBER_WORDS) and typ not in ("number",) and not free_text:
            findings["E2"].append(f"{rel}:{ln} label '{label}' type={typ} -> sebaiknya type=number")
        if has_word(low, DATE_WORDS) and typ not in ("date", "datetime-local", "month") \
                and typ != "number":
            # `typ != "number"`: field yang JELAS angka bukan tanggal walau labelnya
            # menyebut tenggat (mis. "Maksimal jumlah tenggat per pelaksana per hari"
            # = batas beban, bukan tanggal).
            findings["E3"].append(f"{rel}:{ln} label '{label}' type={typ} -> sebaiknya type=date")


def audit_hardcoded_vocab(rel: str, src: str):
    """E5 — peta label enum hardcode padahal grup-nya sudah ada di SSOT.

    Hanya menandai peta yang isinya benar-benar LABEL manusia (nilai string berawalan
    huruf kapital, mis. "Terbuka"). Peta nada warna (`"in_progress"`), peta alur tahap
    (`{acquisition: "nurturing"}`) dan peta ikon (nilai bukan string) BUKAN duplikasi label
    sehingga tidak dilaporkan.
    """
    if rel.replace("\\", "/") in ALLOW_E5_FILES:
        return
    group_values = {g: set(ref.values(g)) for g in ref.GROUPS}
    all_values = set().union(*group_values.values()) if group_values else set()
    for m in re.finditer(r"const\s+([A-Z][A-Z0-9_]*)\s*=\s*\{([^}]{10,900})\}", src):
        name, body = m.group(1), m.group(2)
        pairs = re.findall(r'[\{,\s]["\']?([a-z_][a-z0-9_-]*)["\']?\s*:\s*"([^"]{2,50})"', body)
        keys = {k for k, _v in pairs}
        human = [v for _k, v in pairs if re.match(r"^[A-Z]", v) and v not in all_values]
        if len(keys) < 2 or len(human) < 2:
            continue
        best, hit = None, set()
        for g, vals in group_values.items():
            common = keys & vals
            if len(common) > len(hit):
                best, hit = g, common
        if best and len(hit) >= 2 and len(hit) >= len(keys) * 0.6:
            findings["E5"].append(
                f"{rel}:{line_of(src, m.start())} const {name} = peta label hardcode untuk "
                f"grup SSOT '{best}' ({', '.join(sorted(hit))}) -> pakai useReference().labelOf/options")

    # Bentuk kedua: daftar opsi hardcode `const X = [{ v: "draft", l: "Draft" }, ...]`
    for m in re.finditer(r"const\s+([A-Z][A-Z0-9_]*)\s*=\s*\[([^\]]{20,900})\]", src):
        name, body = m.group(1), m.group(2)
        vals = set(re.findall(r'\b[vV](?:alue)?\s*:\s*["\']([a-z_][a-z0-9_.-]*)["\']', body))
        if len(vals) < 2:
            continue
        best, hit = None, set()
        for g, gv in group_values.items():
            common = vals & gv
            if len(common) > len(hit):
                best, hit = g, common
        if best and len(hit) >= 2 and len(hit) >= (len(vals) - 1) * 0.7:
            findings["E5"].append(
                f"{rel}:{line_of(src, m.start())} const {name} = daftar opsi hardcode untuk "
                f"grup SSOT '{best}' ({', '.join(sorted(hit))}) -> pakai ReferenceSelect/options()")

    # Bentuk ketiga (Audit Tahap 7 §3 / CFG-04): opsi <SelectItem value="draft">Draft</SelectItem>
    # diketik langsung di dalam <SelectContent> padahal grupnya ada di SSOT. Item non-kosakata
    # ("all", "__all__", "__new__") tidak dihitung. Pakai <ReferenceItems group=…/>.
    for m in re.finditer(r"<SelectContent[^>]*>(.*?)</SelectContent>", src, re.S):
        body = m.group(1)
        vals = set(re.findall(r'<SelectItem\b[^>]*\bvalue=["\']([a-z_][a-z0-9_.-]*)["\']', body))
        vals -= {"all", "__all__", "__new__", "none"}
        if len(vals) < 2:
            continue
        best, hit = None, set()
        for g, gv in group_values.items():
            common = vals & gv
            if len(common) > len(hit):
                best, hit = g, common
        if best and len(hit) >= 2 and len(hit) >= len(vals) * 0.6:
            findings["E6"].append(
                f"{rel}:{line_of(src, m.start())} <SelectItem> hardcode untuk grup SSOT '{best}' "
                f"({', '.join(sorted(hit))}) -> pakai <ReferenceItems group=\"{best}\" />")


def main():
    files = [p for p in FE.rglob("*.js") if not any(s in p.parts for s in SKIP_DIRS)]
    for f in sorted(files):
        src = f.read_text(encoding="utf-8", errors="ignore")
        rel = str(f.relative_to(FE))
        if "<Input" in src:
            audit_inputs(rel, src)
        audit_hardcoded_vocab(rel, src)

    print("AUDIT FORM MENDALAM (frontend)\n" + "-" * 60)
    for code, title in (("E1", "Harus dropdown (BLOCKING)"),
                        ("E5", "Vocabulary enum hardcode (BLOCKING)"),
                        ("E6", "<SelectItem> enum hardcode (BLOCKING)"),
                        ("E2", "Sebaiknya type=number"),
                        ("E3", "Sebaiknya type=date"),
                        ("E4", "Tanpa label/placeholder/aria-label")):
        items = findings[code]
        print(f"\n{code} — {title}: {len(items)}")
        for it in items:
            print(f"  - {it}")
    print("-" * 60)
    blocking = len(findings["E1"]) + len(findings["E5"]) + len(findings["E6"])
    if blocking:
        print(f"AUDIT FORM GAGAL: {len(findings['E1'])} field enum masih input bebas, "
              f"{len(findings['E5'])} peta label hardcode, {len(findings['E6'])} dropdown hardcode")
        return 1
    print("AUDIT FORM LULUS: semua field enum memakai dropdown SSOT & tidak ada vocabulary hardcode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
