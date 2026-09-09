import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Lock, LockOpen, ShieldAlert, ShieldOff, ExternalLink, Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import StatusPill from "@/components/patterns/StatusPill";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import RetentionWaiveDialog from "@/components/subcon/RetentionWaiveDialog";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import { newRef } from "@/services/offlineSync";
import api from "@/services/apiClient";
import { SUBFIN as T, P51 } from "@/constants/testIds";

/**
 * RetentionsPanel — daftar retensi + GERBANG pencairan.
 *
 * Fase 48C: retensi tidak lagi menumpuk di tagihan tanpa daftar; tiap termin yang disetujui
 * melahirkan baris di sini beserta SEBAB kalau belum bisa dicairkan.
 *
 * Fase 51A menambah kenyataan yang paling penting bagi perusahaan: **klaim garansi yang
 * masih berjalan MENAHAN pencairan**. Retensi adalah satu-satunya alat tekan yang dimiliki
 * pengembang terhadap subkon; kalau ia cair tepat saat rumah sedang diperbaiki karena cacat
 * pekerjaan subkon itu, alat tekannya hilang persis ketika dibutuhkan. Layar ini karena itu:
 *   1. MENUNJUK klaim mana yang menahan (nomor + judul + status), bukan "ada kendala",
 *   2. memberi jalan ke papan garansi supaya klaimnya bisa ditindak,
 *   3. menyediakan PENGABAIAN beralasan untuk peran ber-izin `override` — dan penahanan
 *      yang sudah diabaikan tetap ditampilkan beserta siapa/kapan/kenapa.
 */
export default function RetentionsPanel() {
  const { can } = useAuth();
  const canRequest = can("subcon_finance", "create");
  const canRelease = can("subcon_finance", "manage");
  const canWaive = can("subcon_finance", "override");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState(null);   // {row, mode}
  const [waiveRow, setWaiveRow] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/subcon/retentions");
      setData(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar retensi.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const s = data?.summary;
  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={T.retentionPanel} className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Retensi ditahan" value={s?.held_value ?? 0} tone="amber" format="idr" />
        <MetricCard label="Sudah dicairkan" value={s?.released_value ?? 0} tone="emerald"
          format="idr" />
        <MetricCard label="Siap dicairkan" value={s?.ready ?? 0} tone="indigo" />
        <MetricCard label="Masih tertahan syarat" value={s?.blocked ?? 0} tone="rose" />
      </div>

      {!data?.data?.length ? (
        <EmptyState icon={Lock} title="Belum ada retensi tercatat"
          description={"Retensi lahir saat termin subkon DISETUJUI. Setiap baris punya masa "
            + "pemeliharaan sendiri dan hanya bisa dicairkan setelah syaratnya terpenuhi — "
            + "termasuk tidak ada klaim garansi yang masih berjalan pada unit lingkup SPK."} />
      ) : (
        <div className="space-y-2">
          {data.data.map((r) => (
            <RetentionRow key={r.id} row={r}
              canRequest={canRequest} canRelease={canRelease} canWaive={canWaive}
              onAction={setAction} onWaive={setWaiveRow} />
          ))}
        </div>
      )}

      <ReasonDialog action={action} onOpenChange={() => setAction(null)}
        onDone={() => { setAction(null); load(); }} />
      <RetentionWaiveDialog row={waiveRow} onOpenChange={() => setWaiveRow(null)}
        onDone={() => { setWaiveRow(null); load(); }} />
    </div>
  );
}

function RetentionRow({ row: r, canRequest, canRelease, canWaive, onAction, onWaive }) {
  const gate = r.gate || {};
  const released = r.state === "released";
  const blocks = gate.blocks || [];
  const waived = gate.waived_blocks || [];
  const warranty = blocks.find((b) => b.code === "warranty_claim_active");
  const adaYangBisaDiabaikan = blocks.some((b) => b.waivable);

  return (
    <div data-testid={T.retentionRow} data-state={r.state} className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{r.retention_number}</span>
            <StatusPill status={r.state} group="retention_state" />
            {r.claim_number ? (
              <span className="text-[11px] text-muted-foreground">dari termin {r.claim_number}</span>
            ) : null}
          </div>
          <p className="mt-0.5 font-medium">{r.subcontractor_name}</p>
          <p className="text-xs text-muted-foreground">
            SPK {r.spk_number} · retensi {r.retention_pct}%
          </p>
          <p data-testid={P51.retentionMaintenanceNote} className="text-xs text-muted-foreground">
            {gate.maintenance_detail}
          </p>
        </div>
        <div className="text-right">
          <p className="font-heading text-lg font-semibold tabular-nums">{formatIDR(r.amount)}</p>
          {released ? (
            <p className="text-[11px] text-emerald-700">
              dicairkan {String(r.released_at || "").slice(0, 10)}
              {r.journal_no ? ` · jurnal ${r.journal_no}` : ""}
            </p>
          ) : null}
        </div>
      </div>

      {!released ? (
        <div data-testid={T.retentionGate}
          className={`mt-3 rounded-lg border p-3 text-sm ${gate.ok
            ? "border-emerald-200 bg-emerald-50 text-emerald-900"
            : "border-amber-200 bg-amber-50 text-amber-900"}`}>
          <p className="flex items-center gap-1.5 font-medium">
            {gate.ok ? <LockOpen className="h-4 w-4" /> : <ShieldAlert className="h-4 w-4" />}
            {gate.ok ? "Syarat pencairan terpenuhi" : "Belum bisa dicairkan"}
          </p>
          {blocks.map((b) => (
            <p key={b.code} className="mt-1 text-xs">• {b.detail}</p>
          ))}
          {gate.ok && !waived.length ? (
            <p className="mt-1 text-xs">
              Masa pemeliharaan lewat, tidak ada temuan punch list terbuka
              {gate.punch_scope ? ` ${gate.punch_scope}` : ""}, dan tidak ada klaim garansi
              berjalan {gate.warranty_scope || ""}.
            </p>
          ) : null}
        </div>
      ) : null}

      {!released && warranty ? (
        <div data-testid={P51.retentionWarrantyHold}
          className="mt-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
          <p className="flex items-center gap-1.5 font-medium">
            <ShieldOff className="h-4 w-4" /> Jaminan mutu ditahan klaim garansi
            <span className="font-normal">
              ({gate.warranty_claim_count} klaim {gate.warranty_scope})
            </span>
          </p>
          <ul className="mt-1.5 space-y-1">
            {(gate.warranty_claims || []).map((c) => (
              <li key={c.number} data-testid={P51.retentionWarrantyClaim}
                className="flex flex-wrap items-center gap-x-2 text-xs">
                <span className="font-mono">{c.number}</span>
                <span>{c.title}</span>
                {c.unit_code ? <span className="text-rose-700/70">· {c.unit_code}</span> : null}
                {c.category_label ? (
                  <span className="text-rose-700/70">· {c.category_label}</span>
                ) : null}
                <span className="rounded-full border border-rose-300 bg-white px-1.5 py-0.5 text-[10px] font-medium">
                  {c.state_label || c.state}
                </span>
              </li>
            ))}
          </ul>
          <Link data-testid={P51.retentionWarrantyLink} to="/construction?tab=warranty"
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-rose-800 hover:underline">
            Buka papan garansi untuk menuntaskan klaim <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
      ) : null}

      {waived.length ? (
        <div data-testid={P51.retentionWaivedBlock}
          className="mt-2 rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs text-violet-900">
          <p className="flex items-center gap-1.5 font-medium">
            <Info className="h-3.5 w-3.5" /> Penahanan yang diabaikan (tetap tercatat untuk audit)
          </p>
          {waived.map((b) => (
            <p key={b.code} className="mt-1">
              • <b>{b.label || b.code}</b> — diabaikan {b.waived_by} pada{" "}
              {String(b.waived_at || "").slice(0, 10)}: “{b.waived_reason}”
            </p>
          ))}
        </div>
      ) : null}

      {!released ? (
        <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
          {adaYangBisaDiabaikan && canWaive ? (
            <Button data-testid={P51.retentionWaiveBtn} size="sm" variant="outline"
              onClick={() => onWaive(r)}>
              Abaikan penahanan…
            </Button>
          ) : null}
          {adaYangBisaDiabaikan && !canWaive ? (
            <p data-testid={P51.retentionWaiveHint} className="text-xs text-muted-foreground">
              Pengabaian penahanan hanya boleh Manajer Keuangan/Direksi — dan sengaja bukan
              orang yang mengajukan pencairan.
            </p>
          ) : null}
          {r.state === "held" && canRequest ? (
            <Button data-testid={T.retentionRequestBtn} size="sm" variant="outline"
              disabled={!gate.ok}
              title={gate.ok ? undefined
                : "Syarat pencairan belum terpenuhi — lihat sebabnya di atas."}
              onClick={() => onAction({ row: r, mode: "request" })}>
              Ajukan pencairan
            </Button>
          ) : null}
          {r.state === "release_requested" && canRelease ? (
            <Button data-testid={T.retentionReleaseBtn} size="sm"
              onClick={() => onAction({ row: r, mode: "release" })}>
              Cairkan retensi
            </Button>
          ) : null}
          {r.state === "release_requested" && !canRelease ? (
            <p className="text-xs text-muted-foreground">
              Menunggu pencairan oleh Manajer Keuangan
              {r.requested_by ? ` (diajukan ${r.requested_by})` : ""}.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ReasonDialog({ action, onOpenChange, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [ref_, setRef_] = useState(null);
  // Penanda kiriman dibuat SEKALI per dialog: klik ganda saat sinyal buruk tidak boleh
  // melahirkan tagihan kedua (pola sama dengan penerbitan BAST di Fase 50).
  useEffect(() => { setReason(""); setRef_(action ? newRef() : null); }, [action]);

  const submit = async () => {
    if (reason.trim().length < 10) {
      toast.error("Alasan minimal 10 huruf — pencairan retensi mengeluarkan uang."); return;
    }
    setBusy(true);
    try {
      const url = action.mode === "request"
        ? `/subcon/retentions/${action.row.id}/request-release`
        : `/subcon/retentions/${action.row.id}/release`;
      const body = action.mode === "request"
        ? { reason: reason.trim() }
        : { reason: reason.trim(), client_ref: ref_ };
      const r = await api.post(url, body);
      toast.success(action.mode === "request"
        ? "Pencairan diajukan ke Manajer Keuangan."
        : `Retensi dicairkan — jurnal ${r.data.journal_no}. Siap dibayar lewat Utang (AP).`);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memproses retensi.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!action} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {action?.mode === "request" ? "Ajukan pencairan retensi" : "Cairkan retensi"}
          </DialogTitle>
          <DialogDescription>
            {action?.row?.retention_number} · {formatIDR(action?.row?.amount)} untuk{" "}
            {action?.row?.subcontractor_name}.
            {action?.mode === "release"
              ? " Pencairan memindahkan Utang Retensi menjadi Utang Usaha yang siap dibayar."
              : " Pengajuan akan diperiksa ulang syaratnya oleh sistem saat dicairkan."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="ret-reason">Alasan</Label>
          <Textarea id="ret-reason" data-testid={T.retentionReason} rows={3} value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="mis. masa pemeliharaan selesai, seluruh temuan sudah diperbaiki & ditutup" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={T.retentionSubmit} onClick={submit} disabled={busy}>
            {busy ? "Memproses…" : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
