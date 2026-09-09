import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { RupiahInput } from "@/components/ui/rupiah-input";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { P80 } from "@/constants/testIds";

const MODES = [
  { code: "unit_addon", label: "Pembangunan unit + add-on pembeli" },
  { code: "unit", label: "Pembangunan unit saja (RAB tipe)" },
  { code: "addon", label: "Hanya add-on (rumah sudah jadi, pembeli menambah add-on)" },
  { code: "fasum", label: "Fasum / fasos (item RAB fasum)" },
  { code: "umum", label: "Biaya umum (item RAB umum)" },
];
const UNIT_MODES = ["unit_addon", "unit", "addon"];

/** SPK berdasar RAB: baris dari RAB tipe unit / add-on deal / item fasum-umum; nilai boleh dioverride dengan alasan. */
export default function SpkFromRabDialog({ open, onOpenChange, onDone }) {
  const [subs, setSubs] = useState([]);
  const [projects, setProjects] = useState([]);
  const [units, setUnits] = useState([]);
  const [boq, setBoq] = useState([]);
  const [form, setForm] = useState({ subcontractor_id: "", project_id: "", title: "", mode: "unit_addon", retention_pct: "5" });
  const [pick, setPick] = useState({});
  const [draft, setDraft] = useState(null);
  const [lines, setLines] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const isUnit = UNIT_MODES.includes(form.mode);

  useEffect(() => {
    if (!open) return;
    setForm({ subcontractor_id: "", project_id: "", title: "", mode: "unit_addon", retention_pct: "5" }); setPick({}); setDraft(null); setLines([]);
    Promise.all([api.get("/subcon/subcontractors", { params: { active: "true" } }), api.get("/projects")])
      .then(([rs, rp]) => { setSubs(rs.data.data || []); setProjects(rp.data.data || []); }).catch(() => {});
  }, [open]);
  useEffect(() => {
    if (!form.project_id) return;
    setPick({}); setDraft(null); setLines([]);
    if (isUnit) api.get("/units", { params: { project_id: form.project_id, limit: 500 } }).then((r) => setUnits(r.data.data || [])).catch(() => setUnits([]));
    else api.get("/boq/items", { params: { project_id: form.project_id, scope: form.mode } }).then((r) => setBoq(r.data.data || [])).catch(() => setBoq([]));
  }, [form.project_id, form.mode, isUnit]);

  const picked = Object.keys(pick).filter((k) => pick[k]);
  const preview = async () => {
    if (!picked.length) { toast.error(isUnit ? "Pilih minimal satu unit." : "Pilih minimal satu item RAB."); return; }
    setBusy(true);
    try {
      const body = { project_id: form.project_id, mode: form.mode, unit_ids: isUnit ? picked : [], boq_item_ids: isUnit ? [] : picked };
      const r = await api.post("/rab/spk-draft", body);
      const d = r.data.data; setDraft(d);
      const ls = isUnit ? d.units.flatMap((u) => u.lines) : d.lines;
      setLines(ls.map((l) => ({ ...l, value: String(l.value), override_reason: "" })));
      if (!form.title) set("title", isUnit ? `SPK ${form.mode === "addon" ? "add-on" : "pembangunan"} unit ${d.units.map((u) => u.unit_code).join(", ")}` : `SPK ${form.mode === "fasum" ? "fasum/fasos" : "biaya umum"}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyusun draf dari RAB."); } finally { setBusy(false); }
  };
  const total = useMemo(() => lines.reduce((s, l) => s + (Number(l.value) || 0), 0), [lines]);
  const rabTotal = useMemo(() => lines.reduce((s, l) => s + (l.rab_amount || 0), 0), [lines]);
  const setLine = (i, patch) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  const submit = async () => {
    if (!form.subcontractor_id || !form.title.trim()) { toast.error("Pilih subkontraktor dan isi judul."); return; }
    if (!lines.length) { toast.error("Susun draf dari RAB dulu."); return; }
    setBusy(true);
    try {
      const r = await api.post("/subcon/spk/from-rab", {
        subcontractor_id: form.subcontractor_id, project_id: form.project_id, title: form.title, spk_kind: form.mode,
        retention_pct: Number(form.retention_pct) || 0, unit_ids: isUnit ? picked : [],
        lines: lines.map((l) => ({ ...l, value: Math.round(Number(l.value) || 0) })),
      });
      const a = r.data.data.auto_scope || {};
      toast.success(`SPK ${r.data.data.spk_number} dibuat (${formatIDR(r.data.data.contract_value)})${a.added ? ` · ${a.added} pekerjaan jadwal otomatis masuk lingkup` : ""}.`);
      if (a.missing_steps?.length) toast.warning(`${a.missing_steps.length} baris RAB bertaut langkah tidak masuk lingkup jadwal (${a.missing_steps.slice(0, 3).join(", ")}) — SPK dibayar borongan lump-sum untuk baris itu.`);
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat SPK."); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={P80.spkRabDialog} className="max-h-[90vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Buat SPK</DialogTitle>
          <DialogDescription>Unit dipilih dari master unit proyek; baris pekerjaan dari RAB tipe unit dan add-on pembeli yang menempel pada deal/unit (dari marketing). Baris ber-kode langkah otomatis masuk lingkup jadwal → progres & termin SPK mengikuti opname. Nilai boleh dioverride dengan alasan.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1.5"><Label>Proyek</Label>
            <Select value={form.project_id} onValueChange={(v) => set("project_id", v)}>
              <SelectTrigger data-testid="spk-rab-project"><SelectValue placeholder="Pilih…" /></SelectTrigger>
              <SelectContent>{projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select></div>
          <div className="space-y-1.5"><Label>Jenis SPK</Label>
            <Select value={form.mode} onValueChange={(v) => set("mode", v)}>
              <SelectTrigger data-testid={P80.spkRabMode}><SelectValue /></SelectTrigger>
              <SelectContent>{MODES.map((m) => <SelectItem key={m.code} value={m.code}>{m.label}</SelectItem>)}</SelectContent></Select></div>
          <div className="space-y-1.5"><Label>Subkontraktor</Label>
            <Select value={form.subcontractor_id} onValueChange={(v) => set("subcontractor_id", v)}>
              <SelectTrigger data-testid="spk-rab-sub"><SelectValue placeholder="Pilih…" /></SelectTrigger>
              <SelectContent>{subs.map((s) => <SelectItem key={s.id} value={s.id}>{s.name} ({s.code})</SelectItem>)}</SelectContent></Select></div>
        </div>
        {form.project_id ? (
          <div className="space-y-2 rounded-lg border p-3">
            <p className="text-xs font-semibold">{isUnit ? `Pilih unit (${units.length})` : `Pilih item RAB ${form.mode} (${boq.length})`}</p>
            <div className="grid max-h-[26vh] grid-cols-2 gap-1 overflow-y-auto sm:grid-cols-3">
              {(isUnit ? units : boq).map((x) => (
                <label key={x.id} data-testid={P80.spkRabUnit} className="flex items-center gap-2 rounded px-1 py-0.5 text-xs hover:bg-secondary">
                  <Checkbox data-testid={P80.spkRabUnitCheck} checked={!!pick[x.id]} onCheckedChange={(v) => setPick((p) => ({ ...p, [x.id]: !!v }))} />
                  {isUnit ? <span>{x.code} <span className="text-muted-foreground">· {x.unit_type_code || x.type} · {x.status}</span>
                    {(x.addon_codes || []).length ? <span data-testid="spk-unit-addons" className="ml-1 rounded-full bg-sky-100 px-1.5 text-[10px] text-sky-800">add-on: {x.addon_codes.join(", ")}</span> : null}</span>
                    : <span>{x.cost_code || "-"} {x.description} <span className="text-muted-foreground">· {formatIDR(x.amount)}</span></span>}
                </label>
              ))}
            </div>
            <Button data-testid={P80.spkRabPreview} size="sm" variant="outline" disabled={busy || !picked.length} onClick={preview}>Susun draf dari RAB</Button>
          </div>
        ) : null}
        {draft ? (
          <div className="space-y-2">
            {isUnit ? draft.units.flatMap((u) => u.warnings.map((w, i) => <p key={`${u.unit_id}-${i}`} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{u.unit_code}: {w}</p>)) : null}
            {!lines.length ? <p data-testid="spk-rab-empty" className="rounded border border-dashed p-3 text-xs text-muted-foreground">Tidak ada baris yang bisa disusun untuk pilihan ini — lengkapi RAB tipe / RAB add-on, atau pilih unit dengan deal aktif yang punya add-on. Tombol "Buat SPK" tetap nonaktif sampai ada baris.</p> : null}
            <div className="max-h-[32vh] overflow-y-auto rounded-lg border">
              {lines.map((l, i) => (
                <div key={i} data-testid={P80.spkRabLine} className="grid grid-cols-12 items-center gap-2 border-b px-2 py-1.5 text-xs last:border-0">
                  <span className="col-span-5 truncate">{l.unit_code ? <b>{l.unit_code} · </b> : null}{l.code ? <span className="font-mono text-[10px]">{l.code} </span> : null}{l.description}
                    <span className="block text-[10px] text-muted-foreground">RAB {formatIDR(l.rab_amount)}{l.source === "addon" ? ` · jual ${formatIDR(l.sell_amount)}` : ""}{l.step_code ? ` · langkah ${l.step_code}` : ""}</span></span>
                  <RupiahInput data-testid={P80.spkRabLineValue} className="col-span-3 h-8 text-xs" value={l.value} onChange={(e) => setLine(i, { value: e.target.value })} />
                  <Input data-testid={P80.spkRabLineReason} className="col-span-4 h-8 text-xs" placeholder={Number(l.value) !== l.rab_amount ? "Alasan override (wajib)" : "sesuai RAB"} disabled={Number(l.value) === l.rab_amount} value={l.override_reason} onChange={(e) => setLine(i, { override_reason: e.target.value })} />
                </div>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="spk-rab-title">Judul SPK</Label><Input id="spk-rab-title" data-testid="spk-rab-title" value={form.title} onChange={(e) => set("title", e.target.value)} /></div>
              <div className="space-y-1.5"><Label htmlFor="spk-rab-retention">Retensi (%)</Label><Input id="spk-rab-retention" type="number" value={form.retention_pct} onChange={(e) => set("retention_pct", e.target.value)} /></div>
            </div>
            <div data-testid={P80.spkRabTotal} className="rounded-lg bg-secondary p-3 text-sm">Nilai kontrak SPK: <b className="tabular-nums">{formatIDR(total)}</b>
              <span className="ml-2 text-xs text-muted-foreground">RAB {formatIDR(rabTotal)} · selisih {formatIDR(total - rabTotal)}</span></div>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={P80.spkRabSubmit} disabled={busy || !lines.length} onClick={submit}>{busy ? "Menyimpan…" : "Buat SPK"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
