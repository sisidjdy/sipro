"""Mesin penomoran terkonfigurasi: pola + token → nomor dokumen / kode master.

Aturan per organisasi disimpan di `numbering_rules` (override atas bawaan registry).
Counter tetap memakai `sequences.next_seq` (atomik). Nama counter dijaga sama dengan
sebelum fase ini sehingga urutan yang sudah berjalan tidak terputus.
"""
import re
from datetime import datetime, timezone

from db import db
from core_utils import now_iso
import sequences as seq
from numbering_registry import (REGISTRY, REGISTRY_BY_KEY, GLOBAL_TOKENS, CONTEXT_TOKENS,
                                RESET_OPTIONS, SEQ_SCOPE_OPTIONS, GROUP_LABELS, registry_for)

ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
_TOKEN_RE = re.compile(r"\{([A-Z_]+)(?::(\d+))?\}")
# token konteks yang MEMISAHKAN counter (per proyek, per vendor, …)
SCOPING_TOKENS = {"PROJECT_CODE", "PROJECT_INITIALS", "CLUSTER_CODE", "BLOCK_CODE", "UNIT_CODE",
                  "UNIT_TYPE_CODE", "CUSTOMER_INITIALS", "VENDOR_CODE", "SUBCON_CODE", "CATEGORY"}
EDITABLE = ("pattern", "prefix", "width", "reset", "seq_scope", "start")
_cache: dict = {}


def invalidate():
    _cache.clear()


def initials(name: str, n: int = 3) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name or "") if w]
    if len(words) == 1:
        return words[0][:n].upper()
    return "".join(w[0] for w in words[:n]).upper()


def seq_alpha(n: int) -> str:
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def tokens_in(pattern: str) -> list:
    return [m.group(1) for m in _TOKEN_RE.finditer(pattern or "")]


def uses_seq(pattern: str) -> bool:
    return any(t in ("SEQ", "SEQ_ALPHA") for t in tokens_in(pattern))


def validate_pattern(pattern: str, allowed_context: list) -> list:
    """→ daftar pesan kesalahan (kosong = sah)."""
    errs = []
    if not (pattern or "").strip():
        return ["Pola tidak boleh kosong."]
    known = {t for t, _, _ in GLOBAL_TOKENS} | set(allowed_context)
    for t in tokens_in(pattern):
        if t not in known:
            errs.append(f"Token {{{t}}} tidak tersedia untuk aturan ini.")
    if re.search(r"\{[^}]*$|^[^{]*\}", pattern):
        errs.append("Kurung kurawal tidak seimbang.")
    return errs


# ------------------------------------------------------------------ aturan
async def _overrides(org: str) -> dict:
    if org not in _cache:
        rows = await db.numbering_rules.find({"org_id": org}, {"_id": 0}).to_list(500)
        _cache[org] = {r["key"]: r for r in rows}
    return _cache[org]


async def effective_rule(org: str, key: str) -> dict:
    base = REGISTRY_BY_KEY[key]
    ov = (await _overrides(org)).get(key) or {}
    rule = {**base, **{k: ov[k] for k in EDITABLE if k in ov and ov[k] is not None}}
    rule["overridden"] = bool(ov)
    rule["updated_by"], rule["updated_at"] = ov.get("updated_by"), ov.get("updated_at")
    rule.setdefault("start", 1)
    return rule


async def list_rules(org: str, context: dict = None) -> list:
    out = []
    for r in REGISTRY:
        rule = await effective_rule(org, r["key"])
        rule["default"] = {k: r.get(k) for k in ("pattern", "prefix", "width", "reset", "seq_scope")}
        rule["default"]["start"] = 1
        rule["group_label"] = GROUP_LABELS.get(r["group"], r["group"])
        rule["preview"], rule["next_seq"] = await preview_in_context(org, rule, context)
        out.append(rule)
    return out


async def preview_in_context(org: str, rule: dict, context: dict = None):
    """Contoh nomor + urut berikutnya memakai counter BER-SCOPE dari konteks nyata
    (proyek yang dipilih); token yang tidak tersedia diisi nilai contoh."""
    dt = _now()
    needed = set(tokens_in(rule["pattern"]))
    tokens = await resolve_context(org, context or {}, needed) if context else {}
    samples = {t: ex for t, (_, ex) in CONTEXT_TOKENS.items()}
    for k, v in tokens.items():
        if v:
            samples[k] = v
    samples["ORG_INITIALS"] = initials((await _doc("orgs", org)).get("name") or org)
    samples["PREFIX"] = rule.get("prefix") or ""
    if rule["key"].startswith("docnum:"):
        samples["TEMPLATE_CODE"] = rule["key"].split(":", 1)[1]
    cscope = _counter_scope(rule["key"], rule, tokens, context) if context else rule["key"]
    n = await seq.peek(cscope, org, _period(rule["reset"], dt)) + 1
    n = max(n, int(rule.get("start") or 1))
    return render(rule["pattern"], samples, n, int(rule["width"]), dt), n


async def save_rule(org: str, key: str, patch: dict, actor: str) -> dict:
    if key not in REGISTRY_BY_KEY:
        raise LookupError("Aturan penomoran tidak dikenal.")
    base = REGISTRY_BY_KEY[key]
    pattern = str(patch.get("pattern") or base["pattern"]).strip()
    errs = validate_pattern(pattern, base["tokens"])
    if key == "master:unit" and "NO" not in tokens_in(pattern) and not uses_seq(pattern):
        errs.append("Kode unit harus memuat {NO} atau {SEQ} agar unik dalam blok.")
    if errs:
        raise ValueError(" ".join(errs))
    reset = patch.get("reset") or base["reset"]
    if reset not in RESET_OPTIONS:
        raise ValueError("Kebijakan reset tidak dikenal.")
    seq_scope = patch.get("seq_scope") or base["seq_scope"]
    if seq_scope not in SEQ_SCOPE_OPTIONS:
        raise ValueError("Cakupan urutan tidak dikenal.")
    width = int(patch.get("width") or base["width"])
    start = int(patch.get("start") or 1)
    if not 1 <= width <= 8 or start < 1:
        raise ValueError("Lebar digit 1–8 dan nomor awal minimal 1.")
    doc = {"org_id": org, "key": key, "pattern": pattern,
           "prefix": (patch.get("prefix") if patch.get("prefix") is not None else base["prefix"]),
           "width": width, "reset": reset, "seq_scope": seq_scope, "start": start,
           "updated_by": actor, "updated_at": now_iso()}
    await db.numbering_rules.update_one({"org_id": org, "key": key}, {"$set": doc}, upsert=True)
    invalidate()
    return await effective_rule(org, key)


async def reset_rule(org: str, key: str) -> dict:
    await db.numbering_rules.delete_one({"org_id": org, "key": key})
    invalidate()
    return await effective_rule(org, key)


# ------------------------------------------------------------------ konteks
def _now():
    return datetime.now(timezone.utc)


def _period(reset: str, dt: datetime):
    if reset == "never":
        return None
    if reset == "monthly":
        return dt.strftime("%Y%m")
    if reset == "daily":
        return dt.strftime("%Y%m%d")
    return dt.strftime("%Y")


async def _doc(coll: str, _id: str) -> dict:
    return (await db[coll].find_one({"id": _id}, {"_id": 0}) or {}) if _id else {}


async def resolve_context(org: str, ctx: dict, needed: set) -> dict:
    """Isi token konteks dari id/nilai yang diberikan pemanggil (hanya yang dipakai pola)."""
    ctx = dict(ctx or {})
    out = {}
    need_proj = needed & {"PROJECT_CODE", "PROJECT_INITIALS"}
    if need_proj and not ctx.get("project_code"):
        pid = ctx.get("project_id")
        if not pid and ctx.get("unit_id"):
            ctx["_unit"] = await _doc("units", ctx["unit_id"])
            pid = ctx["_unit"].get("project_id")
        proj = await _doc("projects", pid)
        ctx.setdefault("project_code", proj.get("code"))
        ctx.setdefault("project_name", proj.get("name"))
    if "PROJECT_CODE" in needed:
        out["PROJECT_CODE"] = (ctx.get("project_code") or "UMUM").upper()
    if "PROJECT_INITIALS" in needed:
        out["PROJECT_INITIALS"] = initials(ctx.get("project_name") or ctx.get("project_code") or "UMUM")
    if needed & {"CLUSTER_CODE", "BLOCK_CODE", "UNIT_CODE", "UNIT_TYPE_CODE"}:
        unit = ctx.get("_unit") or (await _doc("units", ctx.get("unit_id")))
        if "CLUSTER_CODE" in needed:
            code = ctx.get("cluster_code") or unit.get("cluster_code")
            if not code and ctx.get("cluster_id"):
                code = (await _doc("clusters", ctx["cluster_id"])).get("code")
            out["CLUSTER_CODE"] = (code or "").upper()
        if "BLOCK_CODE" in needed:
            code = ctx.get("block_code") or unit.get("block")
            if not code and ctx.get("block_id"):
                code = (await _doc("blocks", ctx["block_id"])).get("code")
            out["BLOCK_CODE"] = (code or "").upper()
        if "UNIT_CODE" in needed:
            out["UNIT_CODE"] = (ctx.get("unit_code") or unit.get("code") or "").upper()
        if "UNIT_TYPE_CODE" in needed:
            out["UNIT_TYPE_CODE"] = (ctx.get("unit_type_code") or unit.get("unit_type_code") or "").upper()
    if "CUSTOMER_INITIALS" in needed:
        name = ctx.get("customer_name") or (await _doc("customers", ctx.get("customer_id"))).get("name")
        out["CUSTOMER_INITIALS"] = initials(name or "", 2)
    if "VENDOR_CODE" in needed:
        out["VENDOR_CODE"] = (ctx.get("vendor_code") or (await _doc("vendors", ctx.get("vendor_id"))).get("code") or "").upper()
    if "SUBCON_CODE" in needed:
        out["SUBCON_CODE"] = (ctx.get("subcon_code") or (await _doc("subcontractors", ctx.get("subcon_id"))).get("code") or "").upper()
    if "ORG_INITIALS" in needed:
        org_doc = await _doc("orgs", org)
        out["ORG_INITIALS"] = initials(org_doc.get("name") or org)
    for tok, key in (("CATEGORY", "category"), ("LEVEL", "level"), ("STAGE", "stage"),
                     ("TEMPLATE_CODE", "template_code"), ("NO", "no")):
        if tok in needed:
            out[tok] = str(ctx.get(key) if ctx.get(key) is not None else "").upper()
    return out


def render(pattern: str, tokens: dict, n: int, width: int, dt: datetime) -> str:
    base = {"YYYY": dt.strftime("%Y"), "YY": dt.strftime("%y"), "MM": dt.strftime("%m"),
            "DD": dt.strftime("%d"), "YYMMDD": dt.strftime("%y%m%d"), "MM_ROMAN": ROMAN[dt.month]}

    def sub(m):
        tok, w = m.group(1), m.group(2)
        if tok == "SEQ":
            return str(n).zfill(int(w) if w else width)
        if tok == "SEQ_ALPHA":
            return seq_alpha(n)
        val = tokens.get(tok, base.get(tok, ""))
        if tok == "NO" and val.isdigit():
            return val.zfill(int(w) if w else 1)
        return val
    return _TOKEN_RE.sub(sub, pattern)


def _counter_scope(scope: str, rule: dict, tokens: dict, ctx: dict = None) -> str:
    if rule["seq_scope"] != "tokens":
        return scope
    parts = [str((ctx or {}).get(k)) for k in rule.get("parent") or [] if (ctx or {}).get(k)]
    parts += [tokens[t] for t in tokens_in(rule["pattern"]) if t in SCOPING_TOKENS and tokens.get(t)]
    return ":".join([scope] + list(dict.fromkeys(parts))) if parts else scope


async def generate(scope: str, org: str, *, prefix: str = None, width: int = None,
                   year: str = None, sep: str = "/", context: dict = None,
                   rule_key: str = None) -> str:
    """Nomor berikutnya untuk `scope`. Tanpa registry → format legacy PREFIX/TAHUN/URUT.

    `rule_key` memaksa aturan tertentu (mis. aturan keluarga `docnum` saat aturan per jenis
    belum diubah) tanpa mengganti nama counter `scope`.
    """
    reg = REGISTRY_BY_KEY.get(rule_key) if rule_key else registry_for(scope)
    dt = _now()
    if year and str(year) != dt.strftime("%Y"):
        dt = dt.replace(year=int(year))
    if not reg:
        n = await seq.next_seq(scope, org, dt.strftime("%Y"))
        return f"{prefix}{sep}{dt.strftime('%Y')}{sep}{str(n).zfill(width or 4)}"
    rule = await effective_rule(org, reg["key"])
    needed = set(tokens_in(rule["pattern"]))
    tokens = await resolve_context(org, context, needed)
    tokens["PREFIX"] = rule["prefix"] if rule["overridden"] and rule["prefix"] else (prefix or rule["prefix"] or "")
    n = 0
    if uses_seq(rule["pattern"]):
        cscope, period = _counter_scope(scope, rule, tokens, context), _period(rule["reset"], dt)
        if int(rule.get("start") or 1) > 1:
            await seq.ensure_at_least(cscope, org, int(rule["start"]) - 1, period)
        n = await seq.next_seq(cscope, org, period)
    w = rule["width"] if rule["overridden"] or width is None else width
    return render(rule["pattern"], tokens, n, w, dt)


async def generate_unique(scope: str, org: str, coll: str, query: dict, context: dict = None,
                          attempts: int = 50) -> str:
    """Kode master yang belum dipakai (`query` = filter pembatas, mis. project_id)."""
    for _ in range(attempts):
        code = await generate(scope, org, context=context)
        if not await db[coll].find_one({**query, "code": code}, {"_id": 1}):
            return code
        if not uses_seq((await effective_rule(org, scope))["pattern"]):
            raise ValueError(f"Kode '{code}' sudah ada.")
    raise ValueError("Tidak menemukan kode unik — periksa pola penomoran.")


async def preview(org: str, rule: dict, sample: dict = None) -> str:
    """Contoh nomor tanpa menaikkan counter (pakai nilai contoh token)."""
    samples = {t: ex for t, (_, ex) in CONTEXT_TOKENS.items()}
    samples["ORG_INITIALS"] = initials((await _doc("orgs", org)).get("name") or org)
    samples.update({k.upper(): str(v) for k, v in (sample or {}).items() if v not in (None, "")})
    samples["PREFIX"] = rule.get("prefix") or ""
    dt = _now()
    n = await seq.peek(rule["key"], org, _period(rule["reset"], dt)) + 1
    return render(rule["pattern"], samples, max(n, int(rule.get("start") or 1)), int(rule["width"]), dt)


def token_catalog(rule_key: str) -> list:
    reg = REGISTRY_BY_KEY[rule_key]
    rows = [{"token": t, "desc": d, "example": ex, "kind": "umum"} for t, d, ex in GLOBAL_TOKENS]
    rows += [{"token": t, "desc": CONTEXT_TOKENS[t][0], "example": CONTEXT_TOKENS[t][1],
              "kind": "konteks"} for t in reg["tokens"]]
    return rows
