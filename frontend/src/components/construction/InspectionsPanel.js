import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ClipboardCheck, Plus, CheckCircle2, XCircle, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import { useAuth } from "@/context/AuthContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { INSPECTION } from "@/constants/testIds";
import RefLabel from "@/components/patterns/RefLabel";
import { useReference } from "@/context/ReferenceContext";


export default function InspectionsPanel({ projectId, phases = [] }) {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canUpdate = can("construction", "update");

  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [tpl, setTpl] = useState("");
  const [phaseId, setPhaseId] = useState("none");
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [insp, tpls] = await Promise.all([
        api.get("/inspections", { params: { project_id: projectId } }),
        api.get("/inspections/templates"),
      ]);
      setRows(insp.data.data || []);
      setSummary(insp.data.summary || null);
      setTemplates(tpls.data.data || []);
    } catch (e) { /* silent */ } finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!tpl) { toast.error("Pilih template inspeksi."); return; }
    setBusy(true);
    try {
      const body = { project_id: projectId, template_code: tpl };
      if (phaseId && phaseId !== "none") body.phase_id = phaseId;
      const r = await api.post("/inspections", body);
      toast.success("Inspeksi dibuat.");
      setNewOpen(false); setTpl(""); setPhaseId("none");
      load();
      setDetail(r.data.data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat inspeksi."); }
    finally { setBusy(false); }
  };

  if (!projectId) return null;

  return (
    <div data-testid={INSPECTION.panel} className="mt-6">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold"><ShieldCheck className="h-4 w-4 text-primary" /> Inspeksi QC</h3>
        {canUpdate ? (
          <Button size="sm" variant="outline" data-testid={INSPECTION.newBtn} onClick={() => setNewOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Inspeksi Baru
          </Button>
        ) : null}
      </div>

      {summary ? (
        <div className="mb-3 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-secondary px-2.5 py-1">Total {summary.total}</span>
          <span className="rounded-full bg-amber-50 px-2.5 py-1 text-amber-700">Berjalan {summary.open}</span>
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-emerald-700">Lulus {summary.passed}</span>
          <span className="rounded-full bg-rose-50 px-2.5 py-1 text-rose-700">Gagal {summary.failed}</span>
        </div>
      ) : null}

      {loading ? <p className="text-sm text-muted-foreground">Memuat…</p> :
        !rows.length ? (
          <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">Belum ada inspeksi untuk proyek ini.</p>
        ) : (
          <div className="space-y-2">
            {rows.map((i) => (
              <button key={i.id} data-testid={INSPECTION.row} onClick={() => setDetail(i)}
                className="flex w-full items-center justify-between rounded-lg border bg-card p-3 text-left hover:bg-accent shadow-[var(--shadow-card)]">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{i.inspection_number} <span className="text-muted-foreground">· <RefLabel group="inspection_category" value={i.category} /></span></p>
                  <p className="text-xs text-muted-foreground">{i.title} · {i.pass_count}/{i.items.length} lulus{i.fail_count ? ` · ${i.fail_count} gagal` : ""}</p>
                </div>
                <StatusPill status={i.status} group="inspection_status" />
              </button>
            ))}
          </div>
        )}

      {/* Create dialog */}
      <Dialog open={newOpen} onOpenChange={setNewOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Inspeksi Baru</DialogTitle>
            <DialogDescription>Pilih template checklist. Item gagal otomatis menjadi punch list.</DialogDescription></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5"><Label>Template</Label>
              <Select value={tpl} onValueChange={setTpl}>
                <SelectTrigger data-testid={INSPECTION.templateSelect}><SelectValue placeholder="Pilih template…" /></SelectTrigger>
                <SelectContent>
                  {templates.map((t) => <SelectItem key={t.code} value={t.code}>{t.name} ({t.items.length} item)</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Fase (opsional)</Label>
              <Select value={phaseId} onValueChange={setPhaseId}>
                <SelectTrigger data-testid={INSPECTION.phaseSelect}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">— Tanpa fase —</SelectItem>
                  {phases.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNewOpen(false)}>Batal</Button>
            <Button data-testid={INSPECTION.createSave} onClick={create} disabled={busy || !tpl}>Buat</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <InspectionDetail inspection={detail} canUpdate={canUpdate}
        onClose={() => setDetail(null)} onChanged={(fresh) => { setDetail(fresh); load(); }} />
    </div>
  );
}

function InspectionDetail({ inspection, canUpdate, onClose, onChanged }) {
  const { options, labelOf } = useReference();
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setItems(inspection?.items ? inspection.items.map((x) => ({ ...x })) : []); }, [inspection]);
  if (!inspection) return null;
  const editable = inspection.status === "in_progress" && canUpdate;
  const setItem = (key, patch) => setItems((arr) => arr.map((it) => (it.key === key ? { ...it, ...patch } : it)));

  const saveItems = async () => {
    setBusy(true);
    try {
      const r = await api.put(`/inspections/${inspection.id}/items`,
        { items: items.map((it) => ({ key: it.key, result: it.result || "pending", note: it.note || null })) });
      toast.success("Hasil item disimpan.");
      onChanged(r.data.data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan."); }
    finally { setBusy(false); }
  };

  const finalize = async () => {
    if (items.some((it) => !it.result || it.result === "pending")) {
      toast.error("Lengkapi semua item dulu (simpan hasil)."); return;
    }
    setBusy(true);
    try {
      await api.put(`/inspections/${inspection.id}/items`,
        { items: items.map((it) => ({ key: it.key, result: it.result, note: it.note || null })) });
      const r = await api.post(`/inspections/${inspection.id}/finalize`);
      const st = r.data.data.status;
      toast.success(st === "failed" ? "Inspeksi GAGAL — punch list dibuat." : "Inspeksi LULUS.");
      onChanged(r.data.data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal finalisasi."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={!!inspection} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid={INSPECTION.detail} className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">{inspection.inspection_number}
            <StatusPill status={inspection.status} group="inspection_status" /></DialogTitle>
          <DialogDescription>{inspection.title} · <RefLabel group="inspection_category" value={inspection.category} />
            {inspection.finalized_at ? ` · selesai ${formatDateTimeWIB(inspection.finalized_at)}` : ""}</DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          {items.map((it) => (
            <div key={it.key} className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm">{it.label || it.key}</span>
                {editable ? (
                  <Select value={it.result || "pending"} onValueChange={(v) => setItem(it.key, { result: v })}>
                    <SelectTrigger data-testid={INSPECTION.itemResult} className="h-8 w-28"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {options("inspection_item_result").map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                ) : (
                  <span className={"inline-flex items-center gap-1 text-sm " + (it.result === "fail" ? "text-rose-600" : it.result === "pass" ? "text-emerald-600" : "text-muted-foreground")}>
                    {it.result === "fail" ? <XCircle className="h-4 w-4" /> : it.result === "pass" ? <CheckCircle2 className="h-4 w-4" /> : null}
                    {labelOf("inspection_item_result", it.result || "pending")}
                  </span>
                )}
              </div>
              {editable ? (
                <Input className="mt-2 h-8" placeholder="Catatan (mis. lokasi masalah)" value={it.note || ""}
                  onChange={(e) => setItem(it.key, { note: e.target.value })} />
              ) : it.note ? <p className="mt-1 text-xs text-muted-foreground">{it.note}</p> : null}
            </div>
          ))}
        </div>

        {editable ? (
          <DialogFooter className="gap-2">
            <Button variant="outline" data-testid={INSPECTION.saveItems} onClick={saveItems} disabled={busy}>Simpan Hasil</Button>
            <Button data-testid={INSPECTION.finalizeBtn} onClick={finalize} disabled={busy}>
              <ClipboardCheck className="mr-1.5 h-4 w-4" /> Finalisasi
            </Button>
          </DialogFooter>
        ) : (
          <p className="text-xs text-muted-foreground">
            {inspection.status === "failed" ? `${inspection.punch_ids?.length || 0} punch item dibuat dari inspeksi ini.` : "Inspeksi telah difinalisasi."}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
