import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ClipboardList, Plus, Trash2, PackageCheck, Check, X, ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import ReqToPoDialog from "@/components/materials/ReqToPoDialog";
import { REQUISITION as T, REQPO } from "@/constants/testIds";

const PILL = {
  submitted: { s: "submitted" }, approved: { s: "approved" },
  partially_issued: { s: "partial", l: "Sebagian Keluar" },
  issued: { s: "issued", l: "Dikeluarkan" }, rejected: { s: "rejected" },
};

function ReqPill({ status }) {
  const m = PILL[status] || { s: status };
  return <StatusPill status={m.s} label={m.l} />;
}

export default function RequisitionsPanel({ projectId, materials, phases, canCreate, canApprove, onChanged }) {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({ total: 0, submitted: 0, approved: 0, issued: 0 });
  const [loading, setLoading] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [poFor, setPoFor] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await api.get(`/materials/requisitions`, { params: { project_id: projectId } });
      setRows(res.data.data || []);
      setSummary(res.data.summary || {});
    } catch (e) { toast.error("Gagal memuat permintaan material."); }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const refresh = () => { load(); onChanged && onChanged(); };

  const act = async (rid, action, body) => {
    setBusy(rid + action);
    try {
      let res;
      if (action === "approve") res = await api.post(`/materials/requisitions/${rid}/approve`, {});
      else if (action === "reject") res = await api.post(`/materials/requisitions/${rid}/reject`, body || {});
      else res = await api.post(`/materials/requisitions/${rid}/issue`, body || {});
      if (action === "issue") {
        const n = res.data.over_budget_materials || 0;
        toast.success(n ? `Material dikeluarkan — ${n} material melebihi RAB!` : "Material dikeluarkan.");
      } else if (action === "approve") toast.success("Permintaan disetujui.");
      else toast.success("Permintaan ditolak.");
      setDetail(null);
      refresh();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal."); }
    finally { setBusy(null); }
  };

  const chips = [
    { k: "total", label: "Total" }, { k: "submitted", label: "Diajukan" },
    { k: "approved", label: "Disetujui" }, { k: "issued", label: "Dikeluarkan" },
  ];

  return (
    <div data-testid={T.panel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {chips.map((c) => (
            <span key={c.k} className="rounded-full border bg-card px-3 py-1 text-xs shadow-[var(--shadow-card)]">
              {c.label}: <b className="tabular-nums">{summary[c.k] ?? 0}</b>
            </span>
          ))}
        </div>
        {canCreate ? (
          <Button data-testid={T.newBtn} size="sm" onClick={() => setNewOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Permintaan Baru
          </Button>
        ) : null}
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Memuat...</p>
      ) : !rows.length ? (
        <EmptyState icon={ClipboardList} title="Belum ada permintaan material"
          description="Ajukan permintaan material dari lapangan untuk disetujui PM lalu dikeluarkan dari gudang." />
      ) : (
        <div className="space-y-2">
          {rows.map((r) => {
            const totReq = r.items.reduce((a, i) => a + Number(i.qty_requested || 0), 0);
            const totIss = r.items.reduce((a, i) => a + Number(i.qty_issued || 0), 0);
            return (
              <div key={r.id} data-testid={T.row}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-3 hover:border-primary/40 shadow-[var(--shadow-card)]">
                <button className="min-w-0 flex-1 text-left" onClick={() => setDetail(r)}>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-muted-foreground">{r.req_number}</span>
                    <ReqPill status={r.status} />
                    {r.phase_name ? <span className="text-[11px] text-muted-foreground">· {r.phase_name}</span> : null}
                  </div>
                  <div className="mt-0.5 truncate text-sm font-medium">{r.purpose || "Permintaan material"}</div>
                  <div className="text-xs text-muted-foreground">
                    {r.items.length} item · diminta {totReq}{totIss ? ` · dikeluarkan ${totIss}` : ""} · oleh {r.requested_by}
                  </div>
                </button>
                <div className="flex items-center gap-1.5">
                  {canApprove && r.status === "submitted" ? (
                    <>
                      <Button data-testid={T.approveBtn} size="sm" variant="outline"
                        disabled={busy === r.id + "approve"} onClick={() => act(r.id, "approve")}>
                        <Check className="mr-1 h-3.5 w-3.5" /> Setujui
                      </Button>
                      <Button data-testid={T.rejectBtn} size="sm" variant="ghost"
                        disabled={busy === r.id + "reject"} onClick={() => act(r.id, "reject", { note: "Ditolak" })}>
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    </>
                  ) : null}
                  {canCreate && ["approved", "partially_issued"].includes(r.status) ? (
                    <>
                      <Button data-testid={T.issueBtn} size="sm"
                        disabled={busy === r.id + "issue"} onClick={() => act(r.id, "issue")}>
                        <PackageCheck className="mr-1 h-3.5 w-3.5" /> Keluarkan
                      </Button>
                      {/* Fase 48B: kalau stok kurang, permintaan ini punya jalan resmi ke
                          pembelian — bukan lagi buntu di layar gudang. */}
                      <Button data-testid={REQPO.shortageBtn} size="sm" variant="outline"
                        onClick={() => setPoFor(r)}>
                        <ShoppingCart className="mr-1 h-3.5 w-3.5" /> Buat PO
                      </Button>
                    </>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <NewRequisitionDialog projectId={projectId} materials={materials} phases={phases}
        open={newOpen} onOpenChange={setNewOpen} onDone={refresh} />

      <ReqToPoDialog requisition={poFor} onOpenChange={(v) => !v && setPoFor(null)}
        onDone={() => { setPoFor(null); refresh(); }} />

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent data-testid={T.detail}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="font-mono text-sm">{detail?.req_number}</span>
              {detail ? <ReqPill status={detail.status} /> : null}
            </DialogTitle>
            <DialogDescription>{detail?.purpose || "Permintaan material"}{detail?.phase_name ? ` · ${detail.phase_name}` : ""}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            {(detail?.items || []).map((it) => {
              const done = Number(it.qty_issued) >= Number(it.qty_requested);
              return (
                <div key={it.material_id} className="flex items-center justify-between rounded-lg border bg-card p-2 text-sm shadow-[var(--shadow-card)]">
                  <div><span className="font-mono text-xs text-muted-foreground">{it.code}</span> <span className="font-medium">{it.name}</span></div>
                  <div className="tabular-nums">
                    <span className={done ? "text-emerald-600" : ""}>{it.qty_issued}</span>
                    <span className="text-muted-foreground"> / {it.qty_requested} {it.uom}</span>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="text-xs text-muted-foreground">
            Diminta oleh {detail?.requested_by} · {detail ? formatDateTimeWIB(detail.created_at) : ""}
            {detail?.approved_by ? <div>Disetujui: {detail.approved_by}</div> : null}
            {detail?.issued_by ? <div>Dikeluarkan: {detail.issued_by}</div> : null}
          </div>
          {["submitted", "approved", "partially_issued"].includes(detail?.status) ? (
            <p className="rounded-lg bg-muted/50 p-2 text-[11px] text-muted-foreground">
              Gunakan tombol aksi di daftar permintaan untuk menyetujui atau mengeluarkan material.
            </p>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function NewRequisitionDialog({ projectId, materials, phases, open, onOpenChange, onDone }) {
  const [purpose, setPurpose] = useState("");
  const [phaseId, setPhaseId] = useState("none");
  const [items, setItems] = useState([{ material_id: "", qty: "" }]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setPurpose(""); setPhaseId("none"); setItems([{ material_id: "", qty: "" }]); }
  }, [open]);

  const setItem = (i, k, v) => setItems((arr) => arr.map((it, idx) => (idx === i ? { ...it, [k]: v } : it)));
  const addRow = () => setItems((arr) => [...arr, { material_id: "", qty: "" }]);
  const rmRow = (i) => setItems((arr) => (arr.length > 1 ? arr.filter((_, idx) => idx !== i) : arr));

  const submit = async () => {
    const valid = items.filter((it) => it.material_id && Number(it.qty) > 0);
    if (!valid.length) { toast.error("Tambahkan minimal 1 material dengan jumlah > 0."); return; }
    setBusy(true);
    try {
      await api.post("/materials/requisitions", {
        project_id: projectId, purpose: purpose || null,
        phase_id: phaseId === "none" ? null : phaseId,
        items: valid.map((it) => ({ material_id: it.material_id, qty: Number(it.qty) })),
      });
      toast.success("Permintaan material diajukan.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Permintaan Material Baru</DialogTitle>
          <DialogDescription>Ajukan kebutuhan material lapangan untuk disetujui PM.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="requisitionspanel-keperluan">Keperluan</Label>
            <Input id="requisitionspanel-keperluan" data-testid={T.purpose} value={purpose} onChange={(e) => setPurpose(e.target.value)}
              placeholder="mis. Pengecoran kolom lantai 2" />
          </div>
          {phases?.length ? (
            <div className="space-y-1.5">
              <Label>Fase (opsional)</Label>
              <Select value={phaseId} onValueChange={setPhaseId}>
                <SelectTrigger data-testid={T.phaseSelect}><SelectValue placeholder="Tanpa fase" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Tanpa fase</SelectItem>
                  {phases.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          ) : null}
          <div className="space-y-2">
            <Label>Item Material</Label>
            {items.map((it, i) => (
              <div key={i} className="flex items-center gap-2">
                <Select value={it.material_id} onValueChange={(v) => setItem(i, "material_id", v)}>
                  <SelectTrigger data-testid={T.itemMaterial} className="flex-1"><SelectValue placeholder="Pilih material" /></SelectTrigger>
                  <SelectContent>
                    {(materials || []).map((m) => (
                      <SelectItem key={m.id} value={m.id}>{m.code} · {m.name} (stok {m.stock} {m.uom})</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input data-testid={T.itemQty} type="number" className="w-24" placeholder="Qty"
                  value={it.qty} onChange={(e) => setItem(i, "qty", e.target.value)} />
                <Button variant="ghost" size="icon" onClick={() => rmRow(i)}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
            <Button data-testid={T.addItem} variant="outline" size="sm" onClick={addRow}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Tambah item
            </Button>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={T.createSave} onClick={submit} disabled={busy}>{busy ? "Mengajukan..." : "Ajukan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
