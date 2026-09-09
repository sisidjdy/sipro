import React from "react";
import { CheckCheck, CircleCheck, Hammer, ShieldX, ThumbsUp, Undo2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import EmptyState from "@/components/patterns/EmptyState";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB, fromNow } from "@/utils/formatters";
import { P50 } from "@/constants/testIds";

const PILL = {
  diajukan: "border-sky-200 bg-sky-50 text-sky-800",
  ditolak: "border-slate-200 bg-slate-100 text-slate-700",
  dikerjakan: "border-amber-200 bg-amber-50 text-amber-900",
  selesai: "border-indigo-200 bg-indigo-50 text-indigo-800",
  diverifikasi: "border-teal-200 bg-teal-50 text-teal-800",
  ditutup: "border-emerald-200 bg-emerald-50 text-emerald-800",
};

/**
 * Daftar klaim garansi + aksi sesuai tahapnya (Fase 50A).
 *
 * Tombol yang muncul mengikuti KEADAAN klaim dan kewenangan pemakai, bukan sekadar
 * ditampilkan lalu ditolak 403 saat ditekan. Klaim yang DITOLAK tetap tampil beserta
 * sebabnya — pembeli berhak melihat jawaban tertulisnya, dan tim berhak belajar dari pola
 * penolakan.
 */
export default function WarrantyClaimList({ claims = [], onAction, emptyHint }) {
  const { can } = useAuth();
  const mayWork = can("warranty", "update");
  const mayApprove = can("warranty", "approve");

  if (!claims.length) {
    return (
      <EmptyState icon={ShieldX} title="Belum ada klaim garansi"
        description={emptyHint || "Klaim muncul di sini begitu pembeli atau tim mengajukan "
          + "keluhan atas bagian yang masih bergaransi."} />
    );
  }

  return (
    <div className="space-y-2">
      {claims.map((c) => (
        <div key={c.id} data-testid={P50.claimRow} data-state={c.state}
          className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold">
                {c.number} · {c.title}
              </p>
              <p className="text-[12px] text-muted-foreground">
                {c.unit_code} · {c.category_label} · {c.source_label} · diajukan{" "}
                {fromNow(c.submitted_at)}
                {c.assigned_to ? ` · dikerjakan ${c.assigned_to}` : ""}
              </p>
              {c.description ? (
                <p className="mt-1 text-[13px] text-muted-foreground">{c.description}</p>
              ) : null}
              {c.state === "ditolak" ? (
                <p data-testid={P50.claimRejectNote}
                  className="mt-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-[12px] text-slate-700">
                  {c.reject_detail || "Ditolak beralasan."}
                </p>
              ) : null}
              {c.warranty_expires_at ? (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Masa garansi bagian ini sampai {formatDateWIB(c.warranty_expires_at)}
                  {c.fix_photos?.length ? ` · ${c.fix_photos.length} foto bukti perbaikan` : ""}
                  {c.verified_by ? ` · diperiksa ${c.verified_by}` : ""}
                  {c.ack_by ? ` · diakui ${c.ack_by}` : ""}
                </p>
              ) : null}
            </div>
            <div className="flex flex-col items-end gap-2">
              <span data-testid={P50.claimState}
                className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                  PILL[c.state] || PILL.ditolak}`}>
                {c.state_label}
              </span>
              <div className="flex flex-wrap justify-end gap-1.5">
                {c.state === "diajukan" && mayWork ? (
                  <>
                    <Button size="sm" className="h-7 px-2 text-[12px]"
                      data-testid={P50.claimDecideBtn}
                      onClick={() => onAction("accept", c)}>
                      <Hammer className="mr-1 h-3 w-3" /> Terima
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 px-2 text-[12px]"
                      data-testid={P50.claimRejectBtn}
                      onClick={() => onAction("reject", c)}>
                      <ShieldX className="mr-1 h-3 w-3" /> Tolak
                    </Button>
                  </>
                ) : null}
                {c.state === "dikerjakan" && mayWork ? (
                  <Button size="sm" className="h-7 px-2 text-[12px]"
                    data-testid={P50.claimCompleteBtn}
                    onClick={() => onAction("complete", c)}>
                    <CircleCheck className="mr-1 h-3 w-3" /> Selesai + bukti
                  </Button>
                ) : null}
                {c.state === "selesai" && mayApprove ? (
                  <>
                    <Button size="sm" className="h-7 px-2 text-[12px]"
                      data-testid={P50.claimVerifyBtn}
                      onClick={() => onAction("verify", c)}>
                      <CheckCheck className="mr-1 h-3 w-3" /> Lulus periksa
                    </Button>
                    <Button size="sm" variant="outline" className="h-7 px-2 text-[12px]"
                      data-testid={P50.claimReworkBtn}
                      onClick={() => onAction("rework", c)}>
                      <Undo2 className="mr-1 h-3 w-3" /> Kembalikan
                    </Button>
                  </>
                ) : null}
                {c.state === "diverifikasi" && mayApprove ? (
                  <Button size="sm" className="h-7 px-2 text-[12px]"
                    data-testid={P50.claimCloseBtn}
                    onClick={() => onAction("close", c)}>
                    <ThumbsUp className="mr-1 h-3 w-3" /> Tutup (diakui pembeli)
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
