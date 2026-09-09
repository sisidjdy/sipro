import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle, Inbox, RefreshCw, RotateCcw, Trash2, Wrench,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import Pagination from "@/components/patterns/Pagination";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import StatusPill from "@/components/patterns/StatusPill";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { useReference } from "@/context/ReferenceContext";
import { OMNI } from "@/constants/testIds";
import ReferenceItems from "@/components/patterns/ReferenceItems";

const TONE = { open: "pending", resolved: "paid", discarded: "cancelled" };

/**
 * CaptureFailuresPanel — antrean LEAD GAGAL MASUK (`capture.failed`).
 *
 * Dulu payload webhook iklan yang cacat dibalas 422 lalu menguap: biaya iklan sudah
 * keluar tetapi leadnya tidak pernah ada di CRM dan tidak ada jejaknya. Di sini setiap
 * kegagalan bisa dilihat alasannya, DIPERBAIKI datanya (nomor/nama/sumber), lalu
 * DIULANG — atau dibuang dengan alasan yang tercatat untuk audit.
 */
export default function CaptureFailuresPanel({ onCountChange }) {
  const { labelOf } = useReference();
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState(null);
  const [page, setPage] = useState({ skip: 0, limit: 10 });
  const [status, setStatus] = useState("open");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [fixes, setFixes] = useState({});
  const [discardFor, setDiscardFor] = useState(null);
  const [discardReason, setDiscardReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/capture/failures", {
        params: { status: status === "all" ? undefined : status, ...page },
      });
      setRows(res.data?.data || []);
      setTotal(res.data?.total || 0);
      setSummary(res.data?.summary || null);
      onCountChange && onCountChange(res.data?.summary?.open || 0);
    } catch (e) {
      // Pesan teknis backend ("tidak memiliki izin 'view_all' pada 'leads'") tidak berguna
      // bagi pengguna. Untuk 403 tampilkan penjelasan manusiawi + siapa yang harus dihubungi.
      setError(e?.response?.status === 403
        ? "Antrean lead gagal masuk hanya bisa dibuka oleh tim Digital Marketing (supervisor/staf) "
          + "dan pemilik. Minta rekan Digital Marketing menyelamatkan lead ini, atau hubungi admin "
          + "bila Anda memang perlu akses."
        : (e?.response?.data?.detail || "Gagal memuat antrean lead gagal masuk."));
    } finally { setLoading(false); }
  }, [status, page, onCountChange]);

  useEffect(() => { load(); }, [load]);

  const startFix = (row) => {
    setOpenId(openId === row.id ? null : row.id);
    const p = row.payload || {};
    setFixes({ name: p.name || "", phone: p.phone || "", source: p.source || "" });
  };

  const retry = async (row) => {
    setBusyId(row.id);
    try {
      const body = openId === row.id ? { fixes } : { fixes: {} };
      const res = await api.post(`/capture/failures/${row.id}/retry`, body);
      toast.success(res.data?.duplicate
        ? "Lead sudah ada sebelumnya (duplikat) — antrean ditutup."
        : "Lead berhasil diselamatkan dan masuk pipeline.");
      setOpenId(null);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengulang pemasukan lead.");
    } finally { setBusyId(null); }
  };

  const discard = async () => {
    if (discardReason.trim().length < 3) {
      toast.error("Alasan wajib diisi (minimal 3 karakter).");
      return;
    }
    setBusyId(discardFor.id);
    try {
      await api.post(`/capture/failures/${discardFor.id}/discard`, { reason: discardReason });
      toast.success("Antrean dibuang — alasannya tercatat untuk audit.");
      setDiscardFor(null);
      setDiscardReason("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuang antrean.");
    } finally { setBusyId(null); }
  };

  return (
    <div data-testid={OMNI.capturePanel} className="space-y-3">
      <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
          <Inbox className="h-4 w-4 text-primary" /> Lead gagal masuk (antrean penyelamatan)
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Webhook iklan yang mengirim data cacat (nomor kosong/pendek, JSON rusak, field salah)
          TIDAK lagi dibuang. Perbaiki datanya lalu ulangi — biaya iklan tidak hangus. Gangguan
          sementara dicoba ulang otomatis maksimal 3 kali setiap 10 menit.
        </p>
        {summary ? (
          <div data-testid={OMNI.captureSummary} className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              { k: "open", label: "Tertahan", v: summary.open, tone: "text-rose-700" },
              { k: "needs_fix", label: "Perlu koreksi", v: summary.needs_fix, tone: "text-amber-700" },
              { k: "resolved", label: "Diselamatkan", v: summary.resolved, tone: "text-emerald-700" },
              { k: "discarded", label: "Dibuang", v: summary.discarded, tone: "text-muted-foreground" },
            ].map((c) => (
              <div key={c.k} className="rounded-lg border bg-card px-2.5 py-1.5 shadow-[var(--shadow-card)]">
                <p className="text-[11px] text-muted-foreground">{c.label}</p>
                <p className={`text-lg font-semibold tabular-nums ${c.tone}`}>{c.v ?? 0}</p>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Label className="text-xs text-muted-foreground">Status</Label>
        <Select value={status} onValueChange={(v) => { setStatus(v); setPage({ skip: 0, limit: page.limit }); }}>
          <SelectTrigger data-testid={OMNI.captureStatusFilter} className="h-8 w-52 text-xs"
            aria-label="Filter status antrean">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua</SelectItem>
            <ReferenceItems group="capture_failure_status" />
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" data-testid={OMNI.captureRefresh} onClick={load}
          disabled={loading}>
          <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Muat ulang
        </Button>
      </div>

      {loading ? (
        <p className="rounded-xl border bg-card p-4 text-sm text-muted-foreground shadow-[var(--shadow-card)]">Memuat antrean…</p>
      ) : error ? (
        <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
          {error}
        </p>
      ) : rows.length === 0 ? (
        <p data-testid={OMNI.captureEmpty}
          className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground shadow-[var(--shadow-card)]">
          Tidak ada lead yang tertahan. Semua payload webhook masuk dengan bersih.
        </p>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r.id} data-testid={OMNI.captureRow}
              className="rounded-xl border bg-card p-3 text-sm shadow-[var(--shadow-card)]">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex flex-wrap items-center gap-2">
                  <b>{labelOf("lead_source", r.provider) || r.provider}</b>
                  <StatusPill status={r.status} group="capture_failure_status"
                    tone={TONE[r.status]} />
                  <StatusPill status={r.kind} group="capture_failure_kind"
                    tone={r.kind === "data" ? "draft" : "pending"} />
                  <span className="text-[11px] text-muted-foreground">
                    {formatDateTimeWIB(r.created_at)} · {r.attempts || 0}× dicoba
                  </span>
                </span>
                <span className="flex flex-wrap gap-1.5">
                  {r.status === "open" ? (
                    <>
                      <Button size="sm" variant="outline" data-testid={OMNI.captureFix}
                        onClick={() => startFix(r)}>
                        <Wrench className="mr-1.5 h-3.5 w-3.5" />
                        {openId === r.id ? "Tutup form" : "Perbaiki data"}
                      </Button>
                      <Button size="sm" data-testid={OMNI.captureRetry} disabled={busyId === r.id}
                        onClick={() => retry(r)}>
                        <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Ulangi
                      </Button>
                      <Button size="sm" variant="ghost" data-testid={OMNI.captureDiscard}
                        disabled={busyId === r.id}
                        onClick={() => { setDiscardFor(r); setDiscardReason(""); }}>
                        <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Buang
                      </Button>
                    </>
                  ) : null}
                </span>
              </div>

              <p className="mt-1.5 flex items-start gap-1.5 text-xs text-rose-900">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {r.reason}
              </p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Data diterima: nama <b className="text-foreground">{r.payload?.name || "—"}</b>
                {" · "}nomor <b className="text-foreground">{r.payload?.phone || "—"}</b>
                {r.payload?.campaign ? ` · campaign ${r.payload.campaign}` : ""}
                {r.lead_id ? ` · lead ${String(r.lead_id).slice(0, 8)}…` : ""}
                {r.discard_reason ? ` · dibuang: ${r.discard_reason}` : ""}
              </p>
              {r.payload?._raw_text ? (
                <pre data-testid={OMNI.captureRaw} data-failure={r.id}
                  className="mt-1 max-h-24 overflow-auto rounded-md border bg-secondary/50 p-2 text-[10px] text-muted-foreground">
                  {String(r.payload._raw_text).slice(0, 400)}
                </pre>
              ) : null}

              {openId === r.id ? (
                <div className="mt-2 grid gap-2 rounded-lg border bg-secondary/30 p-2.5 sm:grid-cols-3">
                  <div className="space-y-1">
                    <Label htmlFor={`nm-${r.id}`} className="text-[11px]">Nama</Label>
                    <Input id={`nm-${r.id}`} data-testid={OMNI.captureFixName} className="h-8 text-xs"
                      value={fixes.name || ""}
                      onChange={(e) => setFixes((f) => ({ ...f, name: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`ph-${r.id}`} className="text-[11px]">Nomor WhatsApp</Label>
                    <Input id={`ph-${r.id}`} data-testid={OMNI.captureFixPhone} className="h-8 text-xs"
                      value={fixes.phone || ""} placeholder="08xxxxxxxxxx"
                      onChange={(e) => setFixes((f) => ({ ...f, phone: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`sr-${r.id}`} className="text-[11px]">Sumber</Label>
                    <ReferenceSelect group="lead_source" value={fixes.source || ""}
                      onChange={(v) => setFixes((f) => ({ ...f, source: v }))}
                      testId={OMNI.captureFixSource} placeholder="Pilih sumber lead…" />
                  </div>
                  <p className="text-[11px] text-muted-foreground sm:col-span-3">
                    Nomor akan dinormalkan ke format +62 dan dipakai sebagai kunci de-duplikasi.
                  </p>
                </div>
              ) : null}
            </div>
          ))}
          <Pagination total={total} skip={page.skip} limit={page.limit}
            label="antrean" testId={OMNI.capturePagination}
            onChange={(p) => setPage(p)} />
        </div>
      )}

      <Dialog open={!!discardFor} onOpenChange={(v) => !v && setDiscardFor(null)}>
        <DialogContent className="bg-background">
          <DialogHeader>
            <DialogTitle>Buang antrean lead gagal masuk</DialogTitle>
            <DialogDescription>
              Dipakai untuk spam/uji coba. Alasan WAJIB — tersimpan permanen untuk audit.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="disc">Alasan</Label>
            <Textarea id="disc" rows={2} data-testid={OMNI.captureDiscardReason}
              value={discardReason} onChange={(e) => setDiscardReason(e.target.value)}
              placeholder="mis. payload uji coba dari tim iklan / nomor spam berulang" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDiscardFor(null)}>Batal</Button>
            <Button variant="destructive" data-testid={OMNI.captureDiscardSubmit}
              onClick={discard} disabled={busyId === discardFor?.id}>
              Buang antrean
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
