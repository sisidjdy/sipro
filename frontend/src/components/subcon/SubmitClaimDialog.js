import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Info } from "lucide-react";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { CLAIMS, OPNAME } from "@/constants/testIds";

/**
 * AJUKAN TERMIN (Fase 33).
 *
 * Untuk SPK yang lingkupnya berbasis item pekerjaan, TIDAK ADA kolom persen: sistem
 * menghitung sendiri dari pekerjaan yang sudah diverifikasi dan belum pernah ditagih,
 * lalu memperlihatkan rinciannya sebelum diajukan. Bila belum ada yang bisa ditagih,
 * alasannya disebutkan (mis. "3 pekerjaan menunggu verifikasi supervisor").
 *
 * SPK lump-sum lama tetap memakai persen kumulatif agar kontrak berjalan tidak dipaksa
 * berubah, dan itu dinyatakan terang-terangan di UI.
 */
export default function SubmitClaimDialog({ open, onOpenChange, onDone, presetSpkId }) {
  const [spks, setSpks] = useState([]);
  const [spkId, setSpkId] = useState("");
  const [preview, setPreview] = useState(null);
  const [loadingPrev, setLoadingPrev] = useState(false);
  const [pct, setPct] = useState("");
  const [period, setPeriod] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSpkId(presetSpkId || ""); setPct(""); setPeriod(""); setPreview(null);
    api.get("/subcon/spk").then((r) => {
      const list = (r.data.data || []).filter(
        (s) => ["active", "draft"].includes(s.status)
          && (s.scope_mode === "items" || (s.progress_pct || 0) < 100));
      setSpks(list);
    }).catch(() => setSpks([]));
  }, [open, presetSpkId]);

  const spk = spks.find((s) => s.id === spkId);
  const itemBased = spk?.scope_mode === "items";

  const loadPreview = useCallback(async () => {
    if (!spkId || !itemBased) { setPreview(null); return; }
    setLoadingPrev(true);
    try {
      const r = await api.get(`/subcon/spk/${spkId}/opname`);
      setPreview(r.data.data);
    } catch (e) {
      setPreview(null);
      toast.error(e?.response?.data?.detail || "Gagal memuat pekerjaan yang bisa ditagih.");
    } finally { setLoadingPrev(false); }
  }, [spkId, itemBased]);
  useEffect(() => { loadPreview(); }, [loadPreview]);

  const [fasumCap, setFasumCap] = useState(null);
  useEffect(() => {
    if (!spkId || itemBased || spk?.spk_kind !== "fasum") { setFasumCap(null); return; }
    api.get(`/rab/spk/${spkId}/fasum-cap`).then((r) => setFasumCap(r.data.data.applies ? r.data.data : null)).catch(() => setFasumCap(null));
  }, [spkId, itemBased, spk?.spk_kind]);

  const estGross = (() => {
    if (itemBased) return preview?.gross || 0;
    if (!spk || !pct) return 0;
    const delta = Number(pct) - (spk.progress_pct || 0);
    return delta > 0 ? Math.round((delta / 100) * (spk.contract_value || 0)) : 0;
  })();

  const submit = async () => {
    if (!spkId) { toast.error("Pilih SPK."); return; }
    if (!itemBased && (!pct || Number(pct) <= (spk?.progress_pct || 0))) {
      toast.error(`Progres harus lebih dari ${spk?.progress_pct || 0}%.`); return;
    }
    setBusy(true);
    try {
      await api.post("/subcon/claims", {
        spk_id: spkId, period: period || undefined,
        progress_pct: itemBased ? undefined : Number(pct),
      });
      toast.success("Termin diajukan.");
      onOpenChange(false); onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengajukan termin.");
    } finally { setBusy(false); }
  };

  const blocked = itemBased && !loadingPrev && !(preview?.lines || []).length;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Ajukan Termin (Progress Claim)</DialogTitle>
          <DialogDescription>
            Untuk SPK berbasis item, nilai termin dihitung sistem dari pekerjaan yang sudah
            diverifikasi — tidak ada persen yang diketik.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label>SPK</Label>
            <Select value={spkId} onValueChange={setSpkId}>
              <SelectTrigger data-testid={CLAIMS.submitSpk}>
                <SelectValue placeholder={spks.length ? "Pilih SPK…" : "Tidak ada SPK aktif"} />
              </SelectTrigger>
              <SelectContent>
                {spks.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.spk_number} · {s.subcontractor_name} ·{" "}
                    {s.scope_mode === "items"
                      ? `per item (siap tagih ${formatIDR(s.scope_claimable_value || 0)})`
                      : `lump-sum ${s.progress_pct || 0}%`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {itemBased ? (
            <div data-testid={OPNAME.preview} className="space-y-2">
              <p className="text-sm font-semibold">Pekerjaan terverifikasi yang bisa ditagih</p>
              {loadingPrev ? (
                <p className="text-sm text-muted-foreground">Menghitung dari bukti kerja…</p>
              ) : (preview?.lines || []).length ? (
                <>
                  <div className="divide-y rounded-lg border">
                    {preview.lines.map((l) => (
                      <div key={l.id} data-testid={OPNAME.previewRow}
                        className="flex items-center justify-between gap-3 p-2.5">
                        <div className="min-w-0">
                          <p className="truncate text-sm">
                            <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
                              {l.step_code}
                            </span>{" "}
                            {l.unit_code} · {l.step_name}
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            diverifikasi {l.verified_by || "-"}
                            {l.cost_code ? ` · RAB ${l.cost_code}` : ""}
                          </p>
                        </div>
                        <span className="tabular-nums text-sm font-medium">
                          {formatIDR(l.value)}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div data-testid={OPNAME.previewTotal} className="rounded-lg bg-secondary p-3 text-sm">
                    Nilai termin <b className="tabular-nums">{formatIDR(preview.gross)}</b> ·
                    retensi {preview.retention_pct}%{" "}
                    <b className="tabular-nums">{formatIDR(preview.retention_est)}</b> · dibayar
                    bersih <b className="tabular-nums">{formatIDR(preview.net_est)}</b>
                  </div>
                </>
              ) : (
                <div data-testid={OPNAME.blocked}
                  className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">
                  <Info className="mt-0.5 h-4 w-4" />
                  <div>
                    <p className="font-semibold">Belum ada pekerjaan yang bisa ditagih.</p>
                    {(preview?.blockers || []).map((b) => (
                      <p key={b.state}>
                        • {b.items} pekerjaan {String(b.label).toLowerCase()} — {formatIDR(b.value)}
                      </p>
                    ))}
                    {preview?.open_claim ? (
                      <p>• masih ada termin {preview.open_claim.claim_number} yang belum selesai</p>
                    ) : null}
                    <p className="mt-1">
                      Pekerjaan harus diajukan pelaksana lalu diverifikasi supervisor dulu
                      (Progres &amp; Mutu Konstruksi).
                    </p>
                  </div>
                </div>
              )}
            </div>
          ) : spk ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="submitclaimdialog-progres-kumulatif">Progres kumulatif (%)</Label>
                <Input id="submitclaimdialog-progres-kumulatif" type="number" data-testid={CLAIMS.submitPct} value={pct}
                  onChange={(e) => setPct(e.target.value)}
                  min={(spk?.progress_pct || 0) + 1} max={100}
                  placeholder={`> ${spk.progress_pct || 0}`} />
                <p className="text-[11px] text-amber-700">
                  SPK lump-sum: nilai dihitung dari selisih persen × nilai kontrak, tanpa
                  ikatan bukti per pekerjaan.
                </p>
                {fasumCap ? (
                  <p data-testid="claim-fasum-cap" data-cap={fasumCap.cap_pct}
                    className={`rounded-md border px-2 py-1 text-[11px] ${pct && Number(pct) > fasumCap.cap_pct ? "border-rose-200 bg-rose-50 text-rose-800" : "border-sky-200 bg-sky-50 text-sky-900"}`}>
                    SPK fasum: termin kumulatif dibatasi progres fase konstruksi —{" "}
                    {fasumCap.phases.map((p) => `${p.name} ${p.progress}%`).join(", ")} → batas <b>{fasumCap.cap_pct}%</b>.
                  </p>
                ) : null}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="submitclaimdialog-periode-opsional">Periode (opsional)</Label>
                <Input id="submitclaimdialog-periode-opsional" data-testid={CLAIMS.submitPeriod} value={period}
                  onChange={(e) => setPeriod(e.target.value)} placeholder="mis. Termin 2" />
              </div>
            </div>
          ) : null}

          {itemBased ? (
            <div className="space-y-1.5">
              <Label htmlFor="submitclaimdialog-periode-opsional-2">Periode (opsional)</Label>
              <Input id="submitclaimdialog-periode-opsional-2" data-testid={CLAIMS.submitPeriod} value={period}
                onChange={(e) => setPeriod(e.target.value)} placeholder="mis. Termin 2" />
            </div>
          ) : null}

          {!itemBased && spk ? (
            <div className="rounded-lg bg-secondary p-3 text-sm">
              Estimasi nilai termin: <span className="font-semibold tabular-nums">{formatIDR(estGross)}</span>
              <span className="text-muted-foreground">
                {" "}(dari {spk.progress_pct || 0}% ke {pct || "–"}%)
              </span>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={CLAIMS.submitSave} onClick={submit}
            disabled={busy || !spkId || blocked}>
            {busy ? "Mengajukan…" : "Ajukan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
