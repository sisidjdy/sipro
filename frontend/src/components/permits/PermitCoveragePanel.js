import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, BellRing, ChevronRight, Plus, RefreshCcw, Settings2, Stamp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import AddPermitDialog from "@/components/permits/AddPermitDialog";
import PermitDetailDialog from "@/components/permits/PermitDetailDialog";
import PermitTypesDialog from "@/components/permits/PermitTypesDialog";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { expiryText, HEALTH_TONE } from "@/utils/permitUi";
import { PERMIT_COVERAGE } from "@/constants/testIds";

/**
 * IZIN YANG BERLAKU UNTUK SATU OBJEK (Fase 46, dok 29 §5).
 *
 * Dipakai di Unit 360 → tab “Dokumen &amp; Izin” dan di halaman Proyek. Menjawab pertanyaan
 * yang dulu tidak bisa dijawab sistem: *“izin apa saja yang berlaku untuk rumah ini, dari
 * tingkat mana, dan mana yang sudah/hampir kedaluwarsa?”*
 *
 * Kejujuran yang dijaga:
 *   * izin **warisan** (dari blok/cluster/proyek) ditandai jelas, bukan diklaim milik unit;
 *   * izin tanpa tanggal berlaku ditulis “masa berlaku belum dicatat” — bukan “aman”;
 *   * daftar izin WAJIB (kebijakan `permit.block_build_without`) ditampilkan beserta
 *     keadaannya, sehingga pemakai tahu mengapa mulai bangun bisa terhalang.
 */
export default function PermitCoveragePanel({ unitId = null, projectId = null,
  blockId = null, clusterId = null, title = "Perizinan yang berlaku" }) {
  const { can } = useAuth();
  const canCreate = can("permits", "create");
  const canUpdate = can("permits", "update");
  const canTypes = can("settings", "manage");
  const [cov, setCov] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [renew, setRenew] = useState(null);
  const [detail, setDetail] = useState(null);
  const [typesOpen, setTypesOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/permits/coverage", {
        params: { unit_id: unitId || undefined, project_id: projectId || undefined,
          block_id: blockId || undefined, cluster_id: clusterId || undefined },
      });
      setCov(r.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat perizinan objek ini.");
    } finally { setLoading(false); }
  }, [unitId, projectId, blockId, clusterId]);

  useEffect(() => { load(); }, [load]);

  const scan = async () => {
    setBusy(true);
    try {
      const r = await api.post("/permits/alerts/scan");
      toast.success(r.data?.message || "Pemeriksaan izin dijalankan.");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menjalankan pemeriksaan izin.");
    } finally { setBusy(false); }
  };

  const chain = cov?.chain?.labels || {};
  const rows = cov?.permits || [];
  const required = cov?.required || [];

  return (
    <div data-testid={PERMIT_COVERAGE.panel} className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-1.5 font-heading text-base font-semibold">
            <Stamp className="h-4 w-4 text-primary" /> {title}
          </h3>
          <p data-testid={PERMIT_COVERAGE.chain} className="text-xs text-muted-foreground">
            {[chain.unit ? `Unit ${chain.unit}` : null,
              chain.block ? chain.block : null,
              chain.cluster ? chain.cluster : null,
              chain.project ? chain.project : null].filter(Boolean).join(" ← ")
              || "objek belum dikenali"}
            {" · izin dicari berjenjang dari unit sampai proyek"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canTypes ? (
            <Button size="sm" variant="ghost" data-testid={PERMIT_COVERAGE.typesBtn}
              onClick={() => setTypesOpen(true)}>
              <Settings2 className="mr-1 h-3.5 w-3.5" /> Jenis izin
            </Button>
          ) : null}
          {canUpdate ? (
            <Button size="sm" variant="outline" data-testid={PERMIT_COVERAGE.scanBtn}
              onClick={scan} disabled={busy}>
              <BellRing className="mr-1 h-3.5 w-3.5" /> Periksa masa berlaku
            </Button>
          ) : null}
          {canCreate ? (
            <Button size="sm" data-testid={PERMIT_COVERAGE.addBtn}
              onClick={() => setAddOpen(true)}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Tambah izin
            </Button>
          ) : null}
        </div>
      </div>

      {required.length ? (
        <div data-testid={PERMIT_COVERAGE.required}
          className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-900">
          <p className="font-semibold">
            Izin WAJIB menurut kebijakan (memblokir mulai bangun):
          </p>
          <ul className="mt-1 space-y-1">
            {required.map((r) => (
              <li key={r.code} data-testid={PERMIT_COVERAGE.requiredRow}
                data-satisfied={r.satisfied ? "true" : "false"}>
                <b>{r.code}</b>{" — "}
                {r.satisfied
                  ? `terpenuhi oleh izin tingkat ${r.scope_label || r.scope} (${r.health_label})`
                  : `BELUM ADA / tidak aktif (${r.health_label})`}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {loading ? (
        <p className="mt-3 text-sm text-muted-foreground">Memuat izin…</p>
      ) : error ? (
        <p className="mt-3 text-sm text-rose-700">{error}</p>
      ) : !rows.length ? (
        <p data-testid={PERMIT_COVERAGE.empty} className="mt-3 text-sm text-muted-foreground">
          Belum ada izin yang menempel pada objek ini maupun induknya — keadaan ini
          <b> belum ada data</b>, bukan “aman”.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {rows.map((p) => (
            <li key={p.id} data-testid={PERMIT_COVERAGE.row} data-health={p.health}
              data-scope={p.scope} role="button" tabIndex={0}
              onClick={() => setDetail(p)}
              onKeyDown={(e) => { if (e.key === "Enter") setDetail(p); }}
              className="flex cursor-pointer flex-wrap items-start justify-between gap-2 rounded-lg border bg-secondary p-2.5 transition-colors hover:border-primary/40 hover:bg-secondary/70">
              <div className="min-w-0">
                <p className="text-sm font-medium">
                  {p.type} · {p.name || "tanpa nama dokumen"}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {(p.scope_type_label || "").split(" (")[0]}
                  {p.scope_object ? ` ${p.scope_object}` : ""}
                  {p.inherited ? " · warisan" : " · milik objek ini"}
                  {p.reference_no ? ` · ${p.reference_no}` : ""}
                  {p.authority ? ` · ${p.authority}` : ""}
                </p>
                <p className={`text-[11px] ${p.expiry_known ? "" : "italic"}`}
                  data-testid={p.expiry_known ? undefined : PERMIT_COVERAGE.noExpiry}>
                  Masa berlaku: {expiryText(p)}
                </p>
                <p className="mt-0.5 inline-flex items-center gap-0.5 text-[11px] font-medium text-primary">
                  Lihat detail & aksi <ChevronRight className="h-3 w-3" />
                </p>
              </div>
              <div className="flex flex-col items-end gap-1.5">
                <div className="flex items-center gap-1.5" data-testid={PERMIT_COVERAGE.health}>
                  <StatusPill status={p.status} group="permit_status" />
                  <StatusPill status={p.health} group="permit_health"
                    tone={HEALTH_TONE[p.health]} />
                </div>
                {canUpdate && ["expiring", "expired"].includes(p.health) ? (
                  <Button size="sm" variant="outline" data-testid={PERMIT_COVERAGE.renewBtn}
                    onClick={(e) => { e.stopPropagation(); setRenew(p); }}>
                    <RefreshCcw className="mr-1 h-3.5 w-3.5" /> Perpanjang
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      {(cov?.warnings || []).length ? (
        <ul className="mt-3 space-y-1.5">
          {cov.warnings.map((w, i) => (
            <li key={i}
              className="flex items-start gap-1.5 rounded-lg border border-rose-200 bg-rose-50 p-2 text-xs text-rose-900">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {w.detail}
            </li>
          ))}
        </ul>
      ) : null}

      <AddPermitDialog open={addOpen} onOpenChange={setAddOpen}
        projects={cov?.chain?.project_id
          ? [{ id: cov.chain.project_id, name: chain.project }] : []}
        presetProjectId={cov?.chain?.project_id}
        presetScope={unitId ? "unit" : blockId ? "block" : clusterId ? "cluster" : "project"}
        presetScopeId={unitId || blockId || clusterId || cov?.chain?.project_id}
        onDone={load} />

      <RenewDialog permit={renew} open={!!renew}
        onOpenChange={(v) => !v && setRenew(null)} onDone={load} />

      <PermitDetailDialog permit={detail} open={!!detail}
        onOpenChange={(v) => !v && setDetail(null)} canUpdate={canUpdate}
        onRenew={(p) => { setDetail(null); setRenew(p); }} onChanged={load} />

      {canTypes ? (
        <PermitTypesDialog open={typesOpen} onOpenChange={setTypesOpen} />
      ) : null}
    </div>
  );
}

function RenewDialog({ permit, open, onOpenChange, onDone }) {
  const [date, setDate] = useState("");
  const [ref, setRef] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setDate(""); setRef(""); setNote(""); } }, [open]);
  if (!permit) return null;

  const run = async () => {
    if (!date) { toast.error("Isi masa berlaku baru."); return; }
    setBusy(true);
    try {
      const r = await api.post(`/permits/${permit.id}/renew`, {
        expiry_at: new Date(date).toISOString(),
        reference_no: ref.trim() || null, note: note.trim() || null,
      });
      toast.success(r.data?.message || "Izin diperpanjang.");
      onOpenChange(false); onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memperpanjang izin.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={PERMIT_COVERAGE.renewDialog} className="bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Perpanjang izin {permit.type}</DialogTitle>
          <DialogDescription>
            Masa berlaku lama ({expiryText(permit)}) tetap tersimpan sebagai riwayat — tidak
            ditimpa diam-diam.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="renew-date">Masa berlaku baru</Label>
            <Input id="renew-date" type="date" data-testid={PERMIT_COVERAGE.renewDate}
              value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="renew-ref">Nomor acuan baru (opsional)</Label>
            <Input id="renew-ref" data-testid={PERMIT_COVERAGE.renewRef} value={ref}
              onChange={(e) => setRef(e.target.value)}
              placeholder="mis. 503/2211/DPMPTSP/2026" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="renew-note">Catatan</Label>
            <Textarea id="renew-note" rows={2} value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="mis. perpanjangan disetujui, dokumen fisik menyusul" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={PERMIT_COVERAGE.renewSubmit} onClick={run}
            disabled={busy || !date}>
            {busy ? "Menyimpan…" : "Perpanjang"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
