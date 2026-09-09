import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { ClipboardCheck, ShieldAlert } from "lucide-react";

import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { formatIDR, formatDateTimeWIB } from "@/utils/formatters";
import { OPNAME } from "@/constants/testIds";

// PENGECUALIAN SAH dari aturan "jangan salin matriks RBAC": `subcon_claims_router`
// menolak opname atas termin yang DIAJUKAN SENDIRI kecuali pelakunya owner/super_admin —
// aturan empat-mata itu ditulis backend memakai NAMA PERAN, bukan izin, sebab tak ada
// izin yang bisa menyatakan "boleh memverifikasi pekerjaannya sendiri". Layar meniru
// aturan yang SAMA supaya tombolnya tidak menjanjikan yang akan ditolak server.
// Kalau backend berubah, ubah keduanya. Dijaga daftar izin di `verify_rbac_ui.py`.
const OWNER_ROLES = ["owner", "super_admin"];

/**
 * OPNAME TERMIN (Fase 33).
 *
 * Opname hanya boleh MENGURANGI baris yang diajukan — tidak bisa menambah pekerjaan baru
 * ke termin yang sudah masuk (itulah celah lama saat opname cuma mengetik persen). Setiap
 * pengurangan wajib beralasan supaya subkontraktor tahu apa yang harus diperbaiki.
 *
 * Untuk SPK lump-sum lama, opname tetap memakai persen kumulatif agar riwayat kontrak
 * yang sudah berjalan tidak dipaksa berubah.
 */
export default function ClaimOpnameSheet({ claim, open, onOpenChange, onDone }) {
  const { user } = useAuth();
  const { labelOf } = useReference();
  const items = claim?.basis === "items";
  const [excluded, setExcluded] = useState({});
  const [reasonCode, setReasonCode] = useState("");
  const [note, setNote] = useState("");
  const [pct, setPct] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!claim) return;
    setExcluded({}); setReasonCode(""); setNote("");
    setPct(claim.claimed_pct || 0);
  }, [claim]);

  const lines = useMemo(() => claim?.lines || [], [claim]);
  const dropIds = useMemo(
    () => Object.keys(excluded).filter((k) => excluded[k]), [excluded]);
  const total = useMemo(() => lines.reduce(
    (a, l) => a + (excluded[l.scope_item_id] ? 0 : Number(l.value || 0)), 0), [lines, excluded]);
  const dropped = (claim?.gross_est || 0) - total;
  const isOwnClaim = claim?.created_by === user?.email && !OWNER_ROLES.includes(user?.nav_role || user?.role);
  const reasonText = [reasonCode ? labelOf("opname_exclude_reason", reasonCode) : "", note]
    .filter(Boolean).join(" — ");
  const needReason = dropIds.length > 0 && reasonText.trim().length < 5;
  const allDropped = items && lines.length > 0 && total <= 0;

  const save = async () => {
    setBusy(true);
    try {
      const body = items
        ? { exclude: dropIds, reason: reasonText || undefined, note: note || undefined }
        : { verified_pct: Number(pct), note: note || undefined };
      await api.post(`/subcon/claims/${claim.id}/verify`, body);
      toast.success(dropIds.length
        ? `Opname disimpan — ${dropIds.length} pekerjaan dikeluarkan.`
        : "Opname disimpan — seluruh pekerjaan lolos pemeriksaan.");
      onOpenChange(false); onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan opname.");
    } finally { setBusy(false); }
  };

  if (!claim) return null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={OPNAME.sheet}
        className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <ClipboardCheck className="h-4 w-4 text-primary" /> Opname {claim.claim_number}
          </SheetTitle>
          <SheetDescription>
            {claim.spk_number} · {claim.subcontractor_name}
            {items ? " — periksa tiap pekerjaan; yang belum layak bisa dikeluarkan (wajib beralasan)."
              : " — SPK borongan lump-sum: isi persen hasil pemeriksaan lapangan."}
          </SheetDescription>
        </SheetHeader>

        {isOwnClaim ? (
          <div data-testid={OPNAME.sodHint}
            className="mt-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">
            <ShieldAlert className="mt-0.5 h-4 w-4" />
            <span>
              Termin ini Anda sendiri yang mengajukan. Pemisahan tugas: opname harus dilakukan
              orang lain (Manajer Proyek) agar pemeriksaan tetap independen.
            </span>
          </div>
        ) : null}

        <div className="mt-4 space-y-4">
          {items ? (
            <>
              <div className="divide-y rounded-lg border">
                {lines.map((l) => {
                  const off = !!excluded[l.scope_item_id];
                  return (
                    <div key={l.scope_item_id} data-testid={OPNAME.line}
                      data-included={off ? "false" : "true"}
                      className="flex items-center gap-3 p-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm">
                          <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
                            {l.step_code}
                          </span>{" "}
                          {l.unit_code} · {l.step_name}
                        </p>
                        <p className="text-[11px] text-muted-foreground">
                          diverifikasi {l.verified_by || "-"}
                          {l.verified_at ? ` · ${formatDateTimeWIB(l.verified_at)}` : ""}
                        </p>
                      </div>
                      <span className={`tabular-nums text-sm ${off ? "text-muted-foreground line-through" : "font-medium"}`}>
                        {formatIDR(l.value)}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <Switch checked={!off} data-testid={OPNAME.toggle}
                          aria-label={`Loloskan ${l.step_code}`}
                          onCheckedChange={(v) => setExcluded((c) => (
                            { ...c, [l.scope_item_id]: !v }))} />
                        <span className="w-10 text-[11px] text-muted-foreground">
                          {off ? "tolak" : "lolos"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {dropIds.length ? (
                <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
                  <Label className="text-[12px]">
                    Alasan {dropIds.length} pekerjaan dikeluarkan (wajib)
                  </Label>
                  <ReferenceSelect group="opname_exclude_reason" value={reasonCode}
                    onChange={setReasonCode} testId={OPNAME.reason}
                    placeholder="Pilih alasan…" />
                  <Textarea data-testid={OPNAME.note} value={note} rows={2}
                    aria-label="Catatan opname"
                    placeholder="Rinci apa yang harus diperbaiki, mis. volume acian kurang 4 m2"
                    onChange={(e) => setNote(e.target.value)} />
                  {needReason ? (
                    <p className="text-[11px] text-rose-700">
                      Isi alasan dulu — subkontraktor perlu tahu apa yang kurang.
                    </p>
                  ) : null}
                </div>
              ) : null}

              <div data-testid={OPNAME.total} className="rounded-lg bg-secondary p-3 text-sm">
                Nilai lolos opname: <b className="tabular-nums">{formatIDR(total)}</b>
                {dropped > 0 ? (
                  <span className="text-muted-foreground">
                    {" "}(dikurangi {formatIDR(dropped)} dari pengajuan {formatIDR(claim.gross_est)})
                  </span>
                ) : null}
                {allDropped ? (
                  <p className="mt-1 text-[12px] text-rose-700">
                    Semua pekerjaan dikeluarkan — lebih jujur menolak termin ini daripada
                    menyetujui nilai nol.
                  </p>
                ) : null}
              </div>
            </>
          ) : (
            <div className="space-y-2">
              <Label>Progres terverifikasi (%)</Label>
              <Input type="number" data-testid={OPNAME.reason} value={pct}
                min={claim.prev_pct} max={claim.claimed_pct}
                aria-label="Progres terverifikasi"
                onChange={(e) => setPct(e.target.value)} />
              <p className="text-[11px] text-muted-foreground">
                Antara {claim.prev_pct}% dan {claim.claimed_pct}% (nilai pengajuan{" "}
                {formatIDR(claim.gross_est)}).
              </p>
              <Textarea data-testid={OPNAME.note} value={note} rows={2}
                aria-label="Catatan opname" placeholder="Catatan hasil pemeriksaan (opsional)"
                onChange={(e) => setNote(e.target.value)} />
            </div>
          )}
        </div>

        <SheetFooter className="mt-5 flex-row justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={OPNAME.save} onClick={save}
            disabled={busy || isOwnClaim || needReason || allDropped}>
            {busy ? "Menyimpan…" : "Simpan hasil opname"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
