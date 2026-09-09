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
import api from "@/services/apiClient";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { formatIDR } from "@/utils/formatters";
import { P75 } from "@/constants/testIds";

const METHOD = { nominal_tetap: "Nominal tetap", persen_harga: "% × harga", rumus_bphtb: "Rumus BPHTB (5% × (harga − NPOPTKP))" };
const TREAT = { developer_borne: "Ditanggung developer (beban)", customer_pass_through: "Ditagih pembeli (titipan)" };
const KOSONG = { code: "", name: "", calc_method: "nominal_tetap", amount: 0, pct: 0, default_treatment: "customer_pass_through",
  gl_expense: "6-1700", gl_liability: "2-1470", gl_ap: "2-1100", kpr_only: false, is_active: true };

/** Master KOMPONEN BIAYA — cara hitung + perlakuan default + akun GL dikunci di sini, bukan diketik sales. */
export default function CostComponentPanel() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/cost-components", { params: { include_inactive: true } }).then((r) => setRows(r.data.data || [])).catch(() => setRows([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...form, amount: Number(form.amount) || 0, pct: Number(form.pct) || 0 };
      if (form.id) await api.put(`/cost-components/${form.id}`, body); else await api.post("/cost-components", body);
      toast.success("Komponen biaya tersimpan."); setForm(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan."); } finally { setBusy(false); }
  };
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="section-title">Komponen biaya transaksi</h3>
          <p className="text-xs text-muted-foreground">BPHTB memakai NPOPTKP per proyek (kolom <code>npoptkp</code> proyek; bawaan dari Konfigurasi Keuangan). Komponen nonaktif tidak mengubah kontrak yang sudah terbit (snapshot).</p>
        </div>
        <Button data-testid={P75.componentAddBtn} size="sm" onClick={() => setForm({ ...KOSONG })}><Plus className="mr-1 h-4 w-4" /> Komponen</Button>
      </div>
      <div data-testid="cost-components-scroll" className="max-w-full overflow-x-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="bg-secondary/60 text-xs uppercase text-muted-foreground">
            <tr><th className="px-3 py-2 text-left">Kode</th><th className="px-3 py-2 text-left">Nama</th><th className="px-3 py-2 text-left">Cara hitung</th><th className="px-3 py-2 text-left">Perlakuan default</th><th className="px-3 py-2 text-left">GL</th><th className="px-3 py-2">Aktif</th><th className="col-actions-head px-3 py-2">Aksi</th></tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((r) => (
              <tr key={r.id} data-testid={P75.componentRow} data-code={r.code} className={r.is_active ? "" : "opacity-50"}>
                <td className="px-3 py-2 font-mono text-xs">{r.code}</td>
                <td className="px-3 py-2">{r.name}{r.kpr_only ? <span className="ml-1 text-[10px] text-muted-foreground">(KPR)</span> : null}</td>
                <td className="px-3 py-2 text-xs">{METHOD[r.calc_method]} {r.calc_method === "nominal_tetap" ? `· ${formatIDR(r.amount)}` : `· ${r.pct}%`}</td>
                <td className="px-3 py-2 text-xs">{TREAT[r.default_treatment]}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{r.gl_expense} / {r.gl_liability} / {r.gl_ap}</td>
                <td className="px-3 py-2 text-center text-xs">{r.is_active ? "ya" : "tidak"}</td>
                <td className="col-actions px-3 py-2 text-right"><Button size="sm" variant="ghost" data-testid={`cost-component-edit-${r.code}`} aria-label={`Ubah komponen ${r.name}`} title={`Ubah komponen ${r.name}`} onClick={() => setForm({ ...r })}><Pencil className="h-3.5 w-3.5" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Dialog open={!!form} onOpenChange={(v) => !v && setForm(null)}>
        <DialogContent className="max-w-lg bg-background">
          <DialogHeader><DialogTitle>{form?.id ? "Ubah" : "Tambah"} komponen biaya</DialogTitle>
            <DialogDescription>Akun GL: beban (developer_borne) / titipan (pass-through) / utang usaha (AP).</DialogDescription></DialogHeader>
          {form ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1"><Label htmlFor="cc-code">Kode</Label><Input id="cc-code" className="bg-background uppercase" value={form.code} disabled={!!form.id} onChange={(e) => set("code", e.target.value.toUpperCase())} /></div>
              <div className="space-y-1"><Label htmlFor="cc-name">Nama</Label><Input id="cc-name" className="bg-background" value={form.name} onChange={(e) => set("name", e.target.value)} /></div>
              <div className="space-y-1"><Label>Cara hitung</Label>
                <Select value={form.calc_method} onValueChange={(v) => set("calc_method", v)}>
                  <SelectTrigger className="bg-background"><SelectValue /></SelectTrigger>
                  <SelectContent>{Object.entries(METHOD).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                </Select></div>
              <div className="space-y-1"><Label>{form.calc_method === "nominal_tetap" ? "Nominal (Rp)" : "Persen (%)"}</Label>
                {form.calc_method === "nominal_tetap"
                  ? <RupiahInput className="bg-background" value={form.amount} onChange={(e) => set("amount", e.target.value)} />
                  : <Input type="number" className="bg-background" value={form.pct} onChange={(e) => set("pct", e.target.value)} />}</div>
              <div className="space-y-1 sm:col-span-2"><Label>Perlakuan default</Label>
                <Select value={form.default_treatment} onValueChange={(v) => set("default_treatment", v)}>
                  <SelectTrigger className="bg-background"><SelectValue /></SelectTrigger>
                  <SelectContent>{Object.entries(TREAT).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                </Select></div>
              <div className="space-y-1"><Label>GL beban</Label><ReferenceSelect group="gl_account" value={form.gl_expense || ""} onChange={(v) => set("gl_expense", v)} testId="cc-gl-expense" /></div>
              <div className="space-y-1"><Label>GL titipan</Label><ReferenceSelect group="gl_account" value={form.gl_liability || ""} onChange={(v) => set("gl_liability", v)} testId="cc-gl-liability" /></div>
              <div className="space-y-1"><Label>GL utang (AP)</Label><ReferenceSelect group="gl_account" value={form.gl_ap || ""} onChange={(v) => set("gl_ap", v)} testId="cc-gl-ap" /></div>
              <div className="flex items-center gap-4 pt-5 text-sm">
                <label className="flex items-center gap-2"><Switch checked={!!form.kpr_only} onCheckedChange={(v) => set("kpr_only", v)} /> Hanya KPR</label>
                <label className="flex items-center gap-2"><Switch checked={!!form.is_active} onCheckedChange={(v) => set("is_active", v)} /> Aktif</label>
              </div>
            </div>
          ) : null}
          <DialogFooter><Button variant="outline" onClick={() => setForm(null)}>Batal</Button>
            <Button data-testid={P75.componentSave} disabled={busy} onClick={save}>Simpan</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
