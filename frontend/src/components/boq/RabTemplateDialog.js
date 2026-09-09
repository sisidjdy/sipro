import React, { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import RabTemplateTools from "./RabTemplateTools";
import RabVersionHistory from "./RabVersionHistory";
import { P80, P81 } from "@/constants/testIds";

const EMPTY_ROW = { code: "", description: "", category: "struktur", uom: "unit", qty: "1", unit_price: "", step_code: "" };
const total = (rows) => rows.reduce((s, r) => s + Math.round((Number(r.qty) || 0) * (Number(r.unit_price) || 0)), 0);
const toRows = (items) => (items || []).map((it) => ({ ...it, qty: String(it.qty), unit_price: String(it.unit_price), step_code: it.step_code || "" }));
const key = (v) => String(v || "").toLowerCase().replace(/[^a-z0-9]/g, "");
const keyMatch = (a, b) => {
  const ka = key(a), kb = key(b);
  if (!ka || !kb) return false;
  if (ka === kb) return true;
  const [s, l] = ka.length <= kb.length ? [ka, kb] : [kb, ka];
  return s.length >= 3 && l.includes(s);
};
const typeTemplates = (steps, target) => steps.filter((t) => t.unit_types.some((x) => keyMatch(x, target?.name) || keyMatch(x, target?.ref_code)));

/** Langkah jadwal tipe ini yang BELUM punya baris RAB — biaya langkah itu tidak masuk anggaran unit. */
function MissingRabPanel({ rows, templates, onAdd, onAddAll }) {
  const used = new Set(rows.map((r) => r.step_code).filter(Boolean));
  const seen = new Set();
  const missing = templates.flatMap((t) => t.steps.filter((s) => !used.has(s.code) && !seen.has(s.code) && seen.add(s.code)));
  if (!templates.length || !missing.length) return null;
  return (
    <div data-testid={P80.tplMissingPanel} className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{missing.length} langkah jadwal belum punya baris RAB</p>
        <Button data-testid={P80.tplMissingAddAll} size="sm" variant="outline" className="h-7 text-xs" onClick={() => onAddAll(missing)}>
          <Plus className="mr-1 h-3 w-3" /> Tambah semua sebagai baris
        </Button>
      </div>
      <p className="mt-0.5 text-[11px]">Langkah tanpa baris RAB tidak punya anggaran — SPK/opname untuk langkah itu tidak bisa dibandingkan dengan rencana. Klik untuk membuat barisnya (isi volume & harga setelahnya).</p>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {missing.map((s) => (
          <button key={s.code} type="button" data-testid={P80.tplMissingStep} data-step={s.code}
            className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-white px-2 py-0.5 text-[11px] hover:bg-amber-100"
            title={`Tambah baris RAB untuk ${s.name}`} onClick={() => onAdd(s)}>
            <Plus className="h-3 w-3" /> {s.code} · {s.name}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Cek sinkron RAB–Jadwal: baris RAB yang kode langkahnya tidak ada di template jadwal tipe ini. */
function SyncWarning({ rows, templates, typeName }) {
  const known = new Set(templates.flatMap((t) => t.steps.map((s) => s.code)));
  const bad = rows.map((r, i) => ({ ...r, i })).filter((r) => r.step_code && !known.has(r.step_code));
  if (!bad.length) return null;
  return (
    <div data-testid={P80.tplSyncWarning} className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
      <p className="font-semibold">RAB belum sinkron dengan template jadwal {typeName}</p>
      {templates.length
        ? <p>{bad.length} baris memakai kode langkah yang tidak ada di {templates.map((t) => t.code).join(", ")}: {bad.map((r) => `${r.code || `#${r.i + 1}`} → ${r.step_code}`).join("; ")}. Baris ini tidak akan tertaut ke jadwal unit (lingkup SPK/opname kosong) — ganti kodenya atau tambahkan langkah di Template Jadwal.</p>
        : <p>Tipe ini belum punya template jadwal aktif, padahal {bad.length} baris RAB menautkan kode langkah ({bad.map((r) => r.step_code).join(", ")}). Buat template jadwal untuk tipe ini di Pembangunan › Template Jadwal.</p>}
    </div>
  );
}

/** Editor RAB tertempel pada TIPE unit atau ADD-ON (kind: unit_type | addon). */
export default function RabTemplateDialog({ kind, target, candidates, open, onOpenChange, onDone }) {
  const [rows, setRows] = useState([]);
  const [steps, setSteps] = useState([]);
  const [tplSource, setTplSource] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState("");
  const [histKey, setHistKey] = useState(0);
  const setRow = (i, patch) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const loadCurrent = () => api.get(`/rab/templates/${kind}/${encodeURIComponent(target.ref_code)}`)
    .then((r) => setRows(toRows(r.data.data.items))).catch(() => setRows([]));

  useEffect(() => {
    if (!open || !target) return;
    setNote(""); setPreview(""); setTplSource("auto");
    loadCurrent();
    if (kind === "unit_type") {
      api.get("/build/templates").then((r) => setSteps((r.data.data || []).filter((t) => t.is_active !== false).map((t) => ({
        code: t.code, name: t.name, unit_types: t.unit_types || [],
        steps: (t.steps || []).map((s) => ({ code: s.code, name: s.name, category: s.category || s.work_category, label: `${s.code} · ${s.name}` })),
      })))).catch(() => setSteps([]));
    }
  }, [open, kind, target]); // eslint-disable-line react-hooks/exhaustive-deps

  const rowFromStep = (s) => ({ ...EMPTY_ROW, code: s.code, description: s.name, step_code: s.code,
    category: s.category || EMPTY_ROW.category, unit_price: "" });
  const addStep = (s) => setRows((rs) => [...rs, rowFromStep(s)]);
  const addAllSteps = (list) => setRows((rs) => [...rs, ...list.map(rowFromStep)]);

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put(`/rab/templates/${kind}/${encodeURIComponent(target.ref_code)}`, {
        note: note || null,
        items: rows.map((r) => ({ ...r, qty: Number(r.qty) || 0, unit_price: Math.round(Number(r.unit_price) || 0), step_code: r.step_code || null })),
      });
      toast.success("RAB tersimpan.");
      const bad = r.data?.sync?.unknown_steps || [];
      if (bad.length) toast.warning(`${bad.length} baris RAB memakai kode langkah yang tidak ada di template jadwal tipe ini (${bad.map((b) => b.step_code).join(", ")}).`);
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan RAB."); } finally { setBusy(false); }
  };
  const autoTemplates = kind === "unit_type" ? typeTemplates(steps, target) : [];
  // Pemakai bisa memilih sendiri template jadwal sumber bila pencocokan otomatis tipe gagal
  // (mis. tipe di template ditulis "30/60" tapi master tipe "Rumah Tapak Premium").
  const ownTemplates = tplSource === "auto" ? autoTemplates : steps.filter((t) => t.code === tplSource);
  const knownCodes = new Set(ownTemplates.flatMap((t) => t.steps.map((s) => s.code)));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P80.tplDialog} className="max-h-[88vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>RAB {kind === "unit_type" ? "tipe" : "add-on"} {target?.ref_code} — {target?.name}</DialogTitle>
          <DialogDescription>
            {kind === "unit_type"
              ? "Biaya membangun SATU unit tipe ini. Proyek mengalikan dengan jumlah unit; SPK unit mengambil baris ini. Kolom langkah menautkan baris ke jadwal pembangunan (acuan harga borongan)."
              : "Biaya (HPP) menyediakan satu add-on ini — dipakai SPK add-on & margin add-on."}
          </DialogDescription>
        </DialogHeader>
        <RabTemplateTools kind={kind} target={target} candidates={candidates}
          onLoadRows={(rs, msg) => { setRows(rs); setPreview(msg); }} />
        {preview ? <p data-testid={P81.previewBanner} className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-800">{preview} <button type="button" className="underline" onClick={() => { loadCurrent(); setPreview(""); }}>Batalkan, muat RAB tersimpan</button></p> : null}
        {kind === "unit_type" && steps.length ? (
          <div data-testid={P80.tplSourceRow} className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">Template jadwal sumber langkah:</span>
            <select data-testid={P80.tplSource} value={tplSource} onChange={(e) => setTplSource(e.target.value)}
              className="h-8 rounded-md border border-input bg-background px-2 text-xs">
              <option value="auto">{autoTemplates.length ? `Otomatis (${autoTemplates.map((t) => t.code).join(", ")})` : "Otomatis — tidak ada yang cocok, pilih manual"}</option>
              {steps.map((t) => <option key={t.code} value={t.code}>{t.code} · {t.name} {t.unit_types.length ? `(${t.unit_types.join(", ")})` : "(semua tipe)"}</option>)}
            </select>
            {!autoTemplates.length && tplSource === "auto" ? (
              <span data-testid={P80.tplSourceHint} className="text-amber-700">Tipe <b>{target?.name}</b> belum tercantum di template jadwal mana pun — pilih template di dropdown, atau tambahkan tipe ini pada template (Pembangunan › Template Jadwal).</span>
            ) : null}
          </div>
        ) : null}
        {kind === "unit_type" ? <SyncWarning rows={rows} templates={ownTemplates} typeName={target?.name} /> : null}
        {kind === "unit_type" ? <MissingRabPanel rows={rows} templates={ownTemplates} onAdd={addStep} onAddAll={addAllSteps} /> : null}
        <div className="space-y-2">
          {rows.map((r, i) => (
            <div key={i} data-testid={P80.tplRow} className="grid grid-cols-12 items-center gap-2 rounded-lg border bg-secondary/40 p-2">
              <Input className="col-span-2 h-8 text-xs" placeholder="Kode" value={r.code} onChange={(e) => setRow(i, { code: e.target.value })} />
              <Input data-testid={P80.tplDesc} className="col-span-3 h-8 text-xs" placeholder="Uraian pekerjaan" value={r.description} onChange={(e) => setRow(i, { description: e.target.value })} />
              <div className="col-span-2"><ReferenceSelect group="work_category" value={r.category} onChange={(v) => setRow(i, { category: v })} /></div>
              <Input data-testid={P80.tplQty} className="col-span-1 h-8 text-xs" type="number" step="0.01" placeholder="Vol" value={r.qty} onChange={(e) => setRow(i, { qty: e.target.value })} />
              <RupiahInput data-testid={P80.tplPrice} className="col-span-3 h-8 text-xs" placeholder="Harga satuan" value={r.unit_price} onChange={(e) => setRow(i, { unit_price: e.target.value })} />
              <Button variant="ghost" size="icon" className="col-span-1 h-8 w-8 text-rose-600" aria-label="Hapus baris" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>
              {kind === "unit_type" ? (
                <select data-testid={P80.tplStep} className={`col-span-6 h-8 rounded-md border bg-background px-2 text-xs ${r.step_code && !knownCodes.has(r.step_code) ? "border-rose-400 text-rose-700" : ""}`} value={r.step_code} onChange={(e) => setRow(i, { step_code: e.target.value })}>
                  <option value="">— tanpa tautan langkah jadwal —</option>
                  {r.step_code && !knownCodes.has(r.step_code)
                    ? <option value={r.step_code} label={`${r.step_code} — bukan langkah jadwal tipe ini (tidak akan masuk lingkup)`}>{`${r.step_code} — bukan langkah jadwal tipe ini (tidak akan masuk lingkup)`}</option> : null}
                  {(ownTemplates.length ? ownTemplates : steps).map((t) => (
                    <optgroup key={t.code} label={`${t.code} — ${t.name}`}>
                      {t.steps.map((s) => <option key={s.code} value={s.code} label={s.label}>{s.label}</option>)}
                    </optgroup>
                  ))}
                </select>
              ) : null}
              {kind === "unit_type" && r.step_code && !knownCodes.has(r.step_code) ? (
                <p data-testid={P80.tplStepMismatch} data-row={i} className="col-span-6 text-right text-[11px] text-rose-700">
                  Langkah {r.step_code} tidak ada di template jadwal tipe ini
                </p>
              ) : (
                <p className="col-span-6 text-right text-xs tabular-nums text-muted-foreground">= {formatIDR(Math.round((Number(r.qty) || 0) * (Number(r.unit_price) || 0)))}</p>
              )}
            </div>
          ))}
          <Button data-testid={P80.tplAddRow} size="sm" variant="outline" onClick={() => setRows((rs) => [...rs, { ...EMPTY_ROW }])}><Plus className="mr-1 h-3.5 w-3.5" /> Tambah baris</Button>
        </div>
        <div data-testid={P80.tplTotal} className="rounded-lg bg-secondary p-3 text-sm">Total RAB per {kind === "unit_type" ? "unit" : "add-on"}: <b className="tabular-nums">{formatIDR(total(rows))}</b>
          {target?.base_price || target?.unit_price ? <span className="ml-2 text-xs text-muted-foreground">· harga jual {formatIDR(target.base_price || target.unit_price)} → margin {formatIDR((target.base_price || target.unit_price) - total(rows))}</span> : null}</div>
        <Input data-testid={P81.tplNote} className="h-8 text-xs" placeholder="Catatan perubahan (opsional, tampil di riwayat versi)" value={note} onChange={(e) => setNote(e.target.value)} />
        <RabVersionHistory kind={kind} target={open ? target : null} reloadKey={histKey}
          onRestored={() => { loadCurrent(); setPreview(""); setHistKey((k) => k + 1); onDone && onDone(); }} />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={P80.tplSave} disabled={busy} onClick={save}>Simpan RAB</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
