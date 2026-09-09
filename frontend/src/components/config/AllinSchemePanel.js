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
import { AllinSchemeItems } from "./AllinSchemeItems";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { P75 } from "@/constants/testIds";

const TR = { developer_borne: "Developer", customer_pass_through: "Pembeli (titipan)" };
const KOSONG = { name: "", note: "", project_ids: [], items: [], is_active: true };

/** Master SKEMA ALL-IN — daftar komponen + perlakuan + override nominal terkunci. Boleh banyak skema. */
export default function AllinSchemePanel() {
  const [rows, setRows] = useState([]);
  const [comps, setComps] = useState([]);
  const [projects, setProjects] = useState([]);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [price, setPrice] = useState(650000000);
  const [preview, setPreview] = useState({});

  const load = useCallback(async () => {
    try {
      const [s, c, p] = await Promise.all([
        api.get("/allin-schemes", { params: { include_inactive: true } }),
        api.get("/cost-components"),
        api.get("/projects", { params: { limit: 100 } }).catch(() => ({ data: { data: [] } })),
      ]);
      setRows(s.data.data || []); setComps(c.data.data || []); setProjects(p.data.data || []);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memuat skema."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const doPreview = async (sid) => {
    try {
      const r = await api.get(`/allin-schemes/${sid}/preview`, { params: { price } });
      setPreview((p) => ({ ...p, [sid]: r.data.data }));
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal pratinjau."); }
  };

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...form, items: form.items.map((it) => ({ ...it, override_amount: it.override_amount === "" || it.override_amount == null ? null : Number(it.override_amount) })) };
      if (form.id) await api.put(`/allin-schemes/${form.id}`, body); else await api.post("/allin-schemes", body);
      toast.success("Skema all-in tersimpan."); setForm(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan."); } finally { setBusy(false); }
  };
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="section-title">Skema all-in / exclude</h3>
          <p className="text-xs text-muted-foreground">Sales memilih skema di SPR; komponen ter-render read-only. "All-in" = biaya ditanggung developer; "Exclude" = pembeli bayar terpisah (titipan). Komponen baru dari tabel di atas otomatis masuk ke setiap skema dengan perlakuan bawaannya.</p>
        </div>
        <div className="flex items-center gap-2">
          <RupiahInput className="w-44 bg-background" value={price} onChange={(e) => setPrice(Number(e.target.value) || 0)} aria-label="Harga contoh" />
          <Button data-testid={P75.schemeAddBtn} size="sm" onClick={() => setForm({ ...KOSONG, items: comps.filter((c) => !c.is_legacy && c.is_active !== false).map((c) => ({ component_code: c.code, treatment: c.default_treatment || "customer_pass_through", override_amount: "" })) })}><Plus className="mr-1 h-4 w-4" /> Skema</Button>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {rows.map((s) => (
          <div key={s.id} data-testid={P75.schemeRow} data-code={s.code} className={`rounded-lg border bg-card p-3 ${s.is_active ? "" : "opacity-50"}`}>
            <div className="flex items-start justify-between gap-2">
              <div><p className="font-medium">{s.name} <span className="font-mono text-[11px] text-muted-foreground">{s.code}</span></p>
                <p className="text-xs text-muted-foreground">{s.note}{s.project_ids?.length ? ` · ${s.project_ids.length} proyek` : " · semua proyek"}</p></div>
              <Button size="sm" variant="ghost" data-testid={`allin-edit-${s.code}`} aria-label={`Ubah skema ${s.name}`} title={`Ubah skema ${s.name}`} onClick={() => setForm({ ...s, items: (s.items || []).map((it) => ({ ...it, override_amount: it.override_amount ?? "" })) })}><Pencil className="h-3.5 w-3.5" /></Button>
            </div>
            <ul className="mt-2 divide-y text-xs">
              {(s.items || []).map((it) => {
                const pv = (preview[s.id]?.components || []).find((c) => c.code === it.component_code);
                const comp = comps.find((c) => c.code === it.component_code);
                return (
                  <li key={it.component_code} className="flex items-center justify-between gap-2 py-1">
                    <span className="min-w-0 truncate">{comp?.name || it.component_code} <span className="font-mono text-[10px] text-muted-foreground">{it.component_code}</span> · {TR[it.treatment]}{it.override_amount ? " · terkunci" : ""}</span>
                    <span className="tabular-nums">{pv ? formatIDR(pv.amount) : "—"}</span>
                  </li>
                );
              })}
            </ul>
            <Button size="sm" variant="outline" className="mt-2" onClick={() => doPreview(s.id)}>Pratinjau @ {formatIDR(price)}</Button>
          </div>
        ))}
      </div>

      <Dialog open={!!form} onOpenChange={(v) => !v && setForm(null)}>
        <DialogContent data-testid="allin-scheme-dialog" className="flex max-h-[90vh] max-w-3xl flex-col bg-background">
          <DialogHeader><DialogTitle>{form?.id ? "Ubah" : "Tambah"} skema all-in</DialogTitle>
            <DialogDescription>Pilih siapa yang menanggung tiap komponen biaya. Nominal pengganti mengunci angka (mengabaikan rumus) untuk skema ini saja.</DialogDescription></DialogHeader>
          {form ? (
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1"><Label htmlFor="allin-name">Nama</Label><Input id="allin-name" className="bg-background" value={form.name} onChange={(e) => set("name", e.target.value)} /></div>
                <div className="space-y-1"><Label htmlFor="allin-note">Catatan</Label><Input id="allin-note" className="bg-background" value={form.note || ""} onChange={(e) => set("note", e.target.value)} /></div>
              </div>
              <div className="space-y-1"><Label>Berlaku untuk proyek (kosong = semua)</Label>
                <div className="flex flex-wrap gap-2">
                  {projects.map((p) => (
                    <label key={p.id} className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs">
                      <input type="checkbox" checked={(form.project_ids || []).includes(p.id)}
                        onChange={(e) => set("project_ids", e.target.checked ? [...(form.project_ids || []), p.id] : (form.project_ids || []).filter((x) => x !== p.id))} />
                      {p.name}
                    </label>
                  ))}
                </div></div>
              <AllinSchemeItems items={form.items} components={comps} onChange={items => set("items", items)} />
              <label className="flex items-center gap-2 text-sm"><Switch checked={!!form.is_active} onCheckedChange={(v) => set("is_active", v)} /> Aktif</label>
            </div>
          ) : null}
          <DialogFooter><Button variant="outline" onClick={() => setForm(null)}>Batal</Button>
            <Button data-testid={P75.schemeSave} disabled={busy || !form?.name?.trim() || !form?.items?.length} onClick={save}>Simpan</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
