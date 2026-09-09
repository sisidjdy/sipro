import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { HardHat } from "lucide-react";

import { Button } from "@/components/ui/button";
import api from "@/services/apiClient";
import { BUILD } from "@/constants/testIds";

/**
 * Ringkasan pembangunan di BERANDA untuk peran proyek.
 *
 * Tujuannya agar keterlambatan dan antrean verifikasi terlihat tanpa harus membuka
 * halaman konstruksi — dulu keduanya hanya muncul kalau seseorang ingat memeriksa.
 */
export default function BuildHealthCard() {
  const navigate = useNavigate();
  const [s, setS] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const r = await api.get("/build/summary");
      setS(r.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat ringkasan pembangunan.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (error) {
    return (
      <div data-testid={BUILD.homeCard}
        className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
        {error}
      </div>
    );
  }
  if (!s) return null;

  const behind = s.avg_progress + 5 < s.avg_planned;

  return (
    <div data-testid={BUILD.homeCard} className="rounded-xl border bg-card p-3 shadow-sm">
      <h2 className="mb-2 flex items-center gap-2 font-heading text-base font-semibold">
        <HardHat className="h-4 w-4 text-primary" /> Pembangunan rumah
      </h2>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <Cell label="Rumah terjadwal" value={`${s.scheduled}/${s.units_total}`}
          hint={s.unscheduled ? `${s.unscheduled} belum dijadwalkan` : "lengkap"}
          tone={s.unscheduled ? "text-amber-700" : "text-emerald-700"} />
        <Cell label="Progres terverifikasi" value={`${s.avg_progress}%`}
          hint={`rencana ${s.avg_planned}%`}
          tone={behind ? "text-rose-700" : "text-emerald-700"} />
        <Cell label="Menunggu verifikasi" value={s.awaiting_verification}
          hint={s.rework ? `${s.rework} minta perbaikan` : "tidak ada perbaikan"}
          tone={s.awaiting_verification ? "text-sky-700" : "text-muted-foreground"} />
        <Cell label="Pekerjaan telat" value={s.late_items}
          hint={`${s.at_risk} unit berisiko`}
          tone={s.late_items ? "text-rose-700" : "text-emerald-700"} />
      </div>
      {s.overrides ? (
        <p className="mt-2 rounded-lg border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-900">
          {s.overrides} gerbang mutu pernah diterobos — semuanya tercatat di jejak audit.
        </p>
      ) : null}
      <Button variant="outline" size="sm" className="mt-2 w-full"
        data-testid={BUILD.homeCardCta} onClick={() => navigate("/construction")}>
        Buka Monitoring Unit
      </Button>
    </div>
  );
}

function Cell({ label, value, hint, tone }) {
  return (
    <div className="rounded-lg border bg-background px-2 py-1.5">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="font-heading text-lg font-semibold tabular-nums">{value}</p>
      <p className={`text-[11px] ${tone}`}>{hint}</p>
    </div>
  );
}
