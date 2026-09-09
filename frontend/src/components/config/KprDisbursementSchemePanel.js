import React, { useCallback, useEffect, useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { P75 } from "@/constants/testIds";

const COND = { akad: "Akad kredit", serah_terima: "Serah terima (BAST)", sertifikat: "Sertifikat" };
const KOSONG = { bank: "", name: "", tolerance_pct: 1, is_active: true,
  tranches: [{ code: "T1", name: "Pencairan akad", pct: 100, amount: 0, condition: "akad" }] };

/** Master SKEMA PENCAIRAN KPR per bank — tahapan (% atau nominal, syarat tahap), total 100%. */
export default function KprDisbursementSchemePanel() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/kpr-disbursement-schemes", { params: { include_inactive: true } }).then((r) => setRows(r.data.data || [])).catch(() => setRows([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...form, tolerance_pct: Number(form.tolerance_pct) || 0,
        tranches: form.tranches.map((t) => ({ ...t, pct: Number(t.pct) || 0, amount: Number(t.amount) || 0 })) };
      if (form.id) await api.put(`/kpr-disbursement-schemes/${form.id}`, body); else await api.post("/kpr-disbursement-schemes", body);
      toast.success("Skema pencairan tersimpan."); setForm(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan."); } finally { setBusy(false); }
  };
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setT = (i, patch) => set("tranches", form.tranches.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  const totalPct = (form?.tranches || []).reduce((s, t) => s + (Number(t.pct) || 0), 0);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="section-title">Skema pencairan KPR per bank</h3>
          <p className="text-xs text-muted-foreground">Kontrak KPR memilih skema → tahapan tergenerasi dari plafon SP3K. Tiap pencairan dipilih dari tahapan (koreksi ±toleransi hanya finance manager).</p>
        </div>
        <Button data-testid={P75.kprSchemeAddBtn} size="sm" onClick={() => setForm({ ...KOSONG, tranches: KOSONG.tranches.map((t) => ({ ...t })) })}><Plus className="mr-1 h-4 w-4" /> Skema</Button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {rows.map((s) => (
          <div key={s.id} data-testid={P75.kprSchemeRow} data-code={s.code} className={`rounded-lg border bg-card p-3 ${s.is_active ? "" : "opacity-50"}`}>
            <div className="flex items-start justify-between gap-2">
              <div><p className="font-medium">{s.name} <span className="font-mono text-[11px] text-muted-foreground">{s.code}</span>
                {s.is_active === false || s.is_active == null ? <span className="ml-2 rounded-full bg-secondary px-2 py-0.5 text-[10px] font-normal">nonaktif</span> : null}</p>
                <p className="text-xs text-muted-foreground">{s.bank || "semua bank"} · toleransi ±{s.tolerance_pct}%</p></div>
              <Button size="sm" variant="ghost" onClick={() => setForm({ ...s })}><Pencil className="h-3.5 w-3.5" /></Button>
            </div>
            <ol className="mt-2 divide-y text-xs">
              {(s.tranches || []).map((t) => (
                <li key={t.code} className="flex items-center justify-between py-1"><span>{t.code} · {t.name} · {COND[t.condition]}</span><span className="tabular-nums">{t.amount ? `Rp ${t.amount.toLocaleString("id-ID")}` : `${t.pct}%`}</span></li>
              ))}
            </ol>
          </div>
        ))}
      </div>

      <Dialog open={!!form} onOpenChange={(v) => !v && setForm(null)}>
        <DialogContent className="max-w-2xl bg-background">
          <DialogHeader><DialogTitle>{form?.id ? "Ubah" : "Tambah"} skema pencairan</DialogTitle>
            <DialogDescription>Total persentase harus 100% (kecuali semua tahap bernominal). Tahap terakhir menyerap pembulatan.</DialogDescription></DialogHeader>
          {form ? (
            <div className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1"><Label htmlFor="kds-name">Nama</Label><Input id="kds-name" className="bg-background" value={form.name} onChange={(e) => set("name", e.target.value)} /></div>
                <div className="space-y-1"><Label>Bank</Label><ReferenceSelect group="financing_bank" value={form.bank || ""} onChange={(v) => set("bank", v)} placeholder="Semua bank" /></div>
                <div className="space-y-1"><Label htmlFor="kds-tolerance">Toleransi koreksi (%)</Label><Input id="kds-tolerance" type="number" step="0.1" className="bg-background" value={form.tolerance_pct} onChange={(e) => set("tolerance_pct", e.target.value)} /></div>
              </div>
              <div className="space-y-2">
                <Label>Tahapan · total {totalPct}%</Label>
                {form.tranches.map((t, i) => (
                  <div key={i} className="grid grid-cols-[70px_1fr_80px_1fr_1fr_auto] items-center gap-2">
                    <Input className="bg-background uppercase" value={t.code} onChange={(e) => setT(i, { code: e.target.value.toUpperCase() })} placeholder="Kode" />
                    <Input className="bg-background" value={t.name} onChange={(e) => setT(i, { name: e.target.value })} placeholder="Nama tahap" />
                    <Input type="number" className="bg-background" value={t.pct} onChange={(e) => setT(i, { pct: e.target.value })} placeholder="%" />
                    <RupiahInput className="bg-background" value={t.amount || ""} onChange={(e) => setT(i, { amount: e.target.value })} placeholder="Nominal (opsional)" />
                    <Select value={t.condition} onValueChange={(v) => setT(i, { condition: v })}>
                      <SelectTrigger className="bg-background"><SelectValue /></SelectTrigger>
                      <SelectContent>{Object.entries(COND).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                    </Select>
                    <Button size="sm" variant="ghost" onClick={() => set("tranches", form.tranches.filter((_, j) => j !== i))}>×</Button>
                  </div>
                ))}
                <Button size="sm" variant="secondary" onClick={() => set("tranches", [...form.tranches, { code: `T${form.tranches.length + 1}`, name: "", pct: 0, amount: 0, condition: "serah_terima" }])}>+ Tahap</Button>
              </div>
              <label className="flex items-center gap-2 text-sm"><Switch checked={!!form.is_active} onCheckedChange={(v) => set("is_active", v)} /> Aktif</label>
            </div>
          ) : null}
          <DialogFooter><Button variant="outline" onClick={() => setForm(null)}>Batal</Button>
            <Button data-testid={P75.kprSchemeSave} disabled={busy || !form?.name} onClick={save}>Simpan</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
