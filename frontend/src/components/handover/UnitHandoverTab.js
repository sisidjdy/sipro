import React, { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import HandoverChecklistPanel from "@/components/handover/HandoverChecklistPanel";
import HandoverDocCard from "@/components/handover/HandoverDocCard";
import WarrantyRows from "@/components/handover/WarrantyRows";
import WarrantyClaimList from "@/components/handover/WarrantyClaimList";
import OfflineQueuePanel from "@/components/construction/OfflineQueuePanel";
import { ClaimActionDialog, ClaimCreateDialog }
  from "@/components/handover/WarrantyClaimDialogs";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { P50 } from "@/constants/testIds";

/**
 * Tab “Serah Terima & Garansi” pada Unit 360 (Fase 50A).
 *
 * Satu tempat untuk seluruh riwayat pasca-bangun satu rumah: apakah boleh diserahkan,
 * dokumen BAST-nya, masa garansi tiap bagian, dan klaim yang pernah masuk. Diletakkan di
 * halaman unit — bukan pintu sidebar baru — karena semuanya adalah kenyataan tentang RUMAH
 * ITU, dan pemakai selalu datang dari kavlingnya.
 */
export default function UnitHandoverTab({ unitId, unitCode }) {
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newClaim, setNewClaim] = useState(false);
  const [action, setAction] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/handover/warranty/unit", { params: { unit_id: unitId } });
      setData(res.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat data serah terima & garansi.");
    } finally { setLoading(false); }
  }, [unitId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const handover = data?.handover;
  const claims = data?.claims || [];

  return (
    <div className="space-y-5">
      <OfflineQueuePanel kinds={["warranty_claim", "warranty_fix"]} />

      {handover ? (
        <HandoverDocCard doc={handover} onChanged={load} />
      ) : (
        <HandoverChecklistPanel unitId={unitId} unitCode={unitCode} onChanged={load} />
      )}

      <div data-testid={P50.warrantyPanel} className="space-y-3">
        <WarrantyRows rows={data?.rows} missing={data?.missing} detail={data?.detail} />
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="section-title">Klaim garansi rumah ini</h3>
            <p className="text-[13px] text-muted-foreground">
              {claims.length
                ? `${claims.length} klaim tercatat · ${data?.summary?.claims_open || 0} masih berjalan`
                : "Belum ada klaim garansi untuk rumah ini."}
            </p>
          </div>
          {handover && can("warranty", "create") ? (
            <Button size="sm" data-testid={P50.claimNewBtn} onClick={() => setNewClaim(true)}>
              <Plus className="mr-1.5 h-3.5 w-3.5" /> Ajukan klaim garansi
            </Button>
          ) : null}
        </div>
        <WarrantyClaimList claims={claims}
          onAction={(mode, claim) => setAction({ mode, claim })}
          emptyHint={handover
            ? "Klaim muncul di sini begitu pembeli atau tim mengajukan keluhan."
            : "Rumah ini belum diserahterimakan, jadi masa garansinya belum mulai."} />
      </div>

      <ClaimCreateDialog open={newClaim} unitId={unitId} unitCode={unitCode}
        onOpenChange={setNewClaim} onDone={load} />
      <ClaimActionDialog mode={action?.mode} claim={action?.claim} open={!!action}
        onOpenChange={(v) => !v && setAction(null)} onDone={load} />
    </div>
  );
}
