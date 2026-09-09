import React, { useCallback, useEffect, useState } from "react";

import UnitReadinessCard from "@/components/build/UnitReadinessCard";
import UnitScheduleView from "@/components/build/UnitScheduleView";
import UnitQualityPanel from "@/components/build/UnitQualityPanel";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { UNIT_BUILD } from "@/constants/testIds";

/**
 * UNIT 360 → tab PEMBANGUNAN (Fase 46, dok 29 §3) — halaman kerja satu rumah.
 *
 * Sebelum fase ini tab ini hanya empat baris read-only (“status”, “progres”, “jadwal”),
 * sehingga semua aksi konstruksi HANYA bisa dijangkau dari layar monitoring lintas unit —
 * bertentangan dengan permintaan owner “harus unit centric”. Sekarang satu tab ini memuat:
 *   1. kesiapan mulai bangun (gerbang DP & izin) + tombol “Mulai bangun” yang beralasan,
 *   2. kurva-S rencana vs realisasi + seluruh langkah kerja beserta aksinya
 *      (mulai, ajukan bukti, verifikasi, tolak, override, sebab telat, hentikan jadwal),
 *   3. mutu: inspeksi QC & temuan (punch) milik unit ini + rapor mingguan proyek.
 */
export default function UnitBuildTab({ unitId, projectId, unitCode, onChanged }) {
  const { can } = useAuth();
  const canStart = can("construction", "approve");
  const [readiness, setReadiness] = useState(null);
  const [tick, setTick] = useState(0);

  const loadReadiness = useCallback(async () => {
    if (!unitId) return;
    try {
      const r = await api.get(`/build/unit/${unitId}/readiness`);
      setReadiness(r.data.data);
    } catch { setReadiness(null); }
  }, [unitId]);

  useEffect(() => { loadReadiness(); }, [loadReadiness]);

  const after = () => {
    loadReadiness();
    setTick((t) => t + 1);
    onChanged?.();
  };

  return (
    <div data-testid={UNIT_BUILD.tab} className="space-y-4">
      <UnitReadinessCard readiness={readiness} canStart={canStart} onChanged={after} />
      <UnitScheduleView key={tick} unitId={unitId} onChanged={after} embedded />
      <UnitQualityPanel unitId={unitId} projectId={projectId} unitCode={unitCode}
        onChanged={after} />
    </div>
  );
}
