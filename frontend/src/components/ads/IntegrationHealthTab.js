import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, PlugZap, ShieldCheck, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useReference } from "@/context/ReferenceContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ADS } from "@/constants/testIds";

/**
 * IntegrationHealthTab — kesiapan integrasi pihak ketiga (spec §1 & §2).
 *
 * Prinsip yang dijaga:
 *  1. **Mode harus terlihat.** Setiap integrasi menyatakan `live` atau `simulasi`; layar lain
 *     yang menampilkan angkanya juga membawa label sumber data.
 *  2. **NILAI kredensial tidak pernah keluar dari server** — yang dilaporkan hanya
 *     “terisi/belum” per nama variabel, jadi halaman ini aman dibuka & di-screenshot.
 *  3. **“Live” tidak boleh sekadar klaim.** Tombol “Uji koneksi” benar-benar memanggil API
 *     platform; kalau tokennya salah, kegagalannya ditampilkan apa adanya.
 *  4. Setiap integrasi menjelaskan apa yang TETAP BERJALAN tanpa kredensial, supaya pemakai
 *     tahu fitur mana yang aman dipakai sekarang.
 */
export default function IntegrationHealthTab() {
  const { labelOf } = useReference();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [probing, setProbing] = useState(false);

  const load = useCallback(async (probe = false) => {
    if (probe) setProbing(true); else setLoading(true);
    setError("");
    try {
      const res = await api.get("/ads/health", { params: probe ? { probe: true } : {} });
      setData(res.data.data);
      if (probe) {
        const live = (res.data.data?.rows || []).filter((r) => r.mode === "live");
        toast.success(live.length
          ? `${live.length} integrasi diuji — lihat kolom hasil uji.`
          : "Semua integrasi masih mode simulasi: tidak ada kredensial untuk diuji.");
      }
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat status integrasi.");
    } finally { setProbing(false); setLoading(false); }
  }, []);

  useEffect(() => { load(false); }, [load]);

  if (loading && !data) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={() => load(false)} />;
  const rows = data?.rows || [];
  if (!rows.length) {
    return <EmptyState icon={PlugZap} title="Belum ada integrasi terdaftar"
      description="Daftar integrasi dibaca dari konfigurasi server." />;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-3xl text-sm text-muted-foreground">
          {data.live_count} integrasi siap live, {data.simulation_count} masih simulasi.
          Mengisi variabel lingkungan TIDAK mengubah kontrak API mana pun — hanya mengubah
          mode. Nilai kredensial tidak pernah ditampilkan di sini.
          {data.last_synced_at
            ? ` Sinkronisasi terakhir: ${formatDateTimeWIB(data.last_synced_at)}.`
            : " Belum pernah ada sinkronisasi dari platform."}
        </p>
        <Button size="sm" variant="outline" data-testid={ADS.healthProbe} disabled={probing}
          onClick={() => load(true)}>
          <ShieldCheck className={`mr-1.5 h-4 w-4 ${probing ? "animate-pulse" : ""}`} />
          {probing ? "Menguji…" : "Uji koneksi"}
        </Button>
      </div>

      <div data-testid={ADS.healthTable} className="grid gap-3 lg:grid-cols-2">
        {rows.map((r) => (
          <div key={r.target} data-testid={ADS.healthRow} data-target={r.target}
            data-mode={r.mode} className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="font-heading text-sm font-semibold">{r.label}</h3>
                <p className="text-xs text-muted-foreground">{r.purpose}</p>
              </div>
              <StatusPill status={r.mode} group="integration_mode"
                tone={r.mode === "live" ? "active" : "simulation"} />
            </div>

            <div className="mt-3 space-y-1">
              {(r.env || []).map((e) => (
                <p key={e.name} className="flex items-center gap-1.5 font-mono text-xs">
                  {e.filled
                    ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                    : <XCircle className="h-3.5 w-3.5 text-muted-foreground" />}
                  <span className={e.filled ? "" : "text-muted-foreground"}>{e.name}</span>
                  <span className="text-muted-foreground">
                    {e.filled ? "terisi" : "belum diisi"}
                  </span>
                </p>
              ))}
            </div>

            {r.mode === "simulation" ? (
              <p className="mt-3 rounded border border-amber-200 bg-amber-50 p-2 text-xs
                text-amber-900">
                <strong>Tanpa kredensial:</strong> {r.fallback}
              </p>
            ) : null}
            {r.healthy === true ? (
              <p className="mt-3 rounded border border-emerald-200 bg-emerald-50 p-2 text-xs
                text-emerald-800">{r.message}</p>
            ) : null}
            {r.healthy === false ? (
              <p className="mt-3 rounded border border-rose-200 bg-rose-50 p-2 text-xs
                text-rose-800">{r.message}</p>
            ) : null}
            {r.mode === "live" && r.healthy === null && r.message ? (
              <p className="mt-3 text-xs text-muted-foreground">{r.message}</p>
            ) : null}
          </div>
        ))}
      </div>

      <p className="text-xs text-muted-foreground">
        Asal angka biaya iklan yang tercatat saat ini:{" "}
        {(data.spend_sources || []).length
          ? (data.spend_sources || []).map((s) => labelOf("ad_spend_source", s)).join(", ")
          : "belum ada biaya iklan yang masuk"}.
      </p>
    </div>
  );
}
