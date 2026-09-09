import React, { useCallback, useEffect, useState } from "react";
import { Database, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/patterns/StateViews";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { AUDIT } from "@/constants/testIds";

/** Angka yang penting dibaca lebih dulu: apakah masih ada unit yang belum dibereskan. */
function StateChip({ label, value, bad = false }) {
  return (
    <span data-testid={AUDIT.migrationState} data-metric={label}
      className={`rounded-full border px-2 py-0.5 text-[11px] ${
        bad && value > 0 ? "border-rose-200 bg-rose-50 text-rose-700"
          : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
      {label}: <b className="tabular-nums">{value}</b>
    </span>
  );
}

function runLines(run) {
  /** Ambil hanya bagian yang berisi angka (bukan meta seperti id/org_id/at). */
  return Object.entries(run)
    .filter(([k, v]) => v && typeof v === "object" && !Array.isArray(v))
    .map(([k, v]) => [k, Object.entries(v)
      .map(([kk, vv]) => `${kk}: ${Array.isArray(vv) ? (vv.join(", ") || "-") : vv}`)
      .join(" · ")]);
}

/**
 * MigrationRunsPanel — riwayat backfill data V2 + KEADAAN SEKARANG.
 *
 * Fase 39 memindahkan unit lama ke struktur cluster/blok/tipe, tetapi hasilnya hanya
 * tercatat di koleksi `migration_runs` tanpa satu pun layar yang menampilkannya. Karena
 * migrasinya idempoten, jalan kedua wajar berangka 0 — jadi panel ini menampilkan hitungan
 * NYATA saat ini lebih dulu (US-39-5: klaim harus bisa diperiksa, bukan dipercaya).
 */
export default function MigrationRunsPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/admin/migrations", { params: { limit: 10 } });
      setData(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat riwayat migrasi data.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const st = data?.state || {};
  const runs = data?.data || [];

  return (
    <section data-testid={AUDIT.migrationPanel} className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Database className="h-4 w-4 text-primary" /> Migrasi & Pembenahan Data (V2)
        </h2>
        <Button size="sm" variant="outline" onClick={load} disabled={loading}
          aria-label="Muat ulang riwayat migrasi">
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Muat ulang
        </Button>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Unit lama dipindahkan ke struktur cluster → blok → tipe unit tanpa kehilangan riwayat.
        Migrasi bersifat idempoten, jadi angka <b>0</b> pada jalan berikutnya berarti
        “tidak ada lagi yang perlu dibereskan” — karena itu keadaan sekarang ditampilkan lebih dulu.
      </p>

      {loading ? (
        <p className="py-3 text-sm text-muted-foreground">Memuat riwayat migrasi…</p>
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-1.5">
            <StateChip label="Unit" value={st.units_total || 0} />
            <StateChip label="Punya cluster" value={st.units_with_cluster || 0} />
            <StateChip label="Punya blok" value={st.units_with_block || 0} />
            <StateChip label="Punya tipe" value={st.units_with_type || 0} />
            <StateChip label="Belum ada cluster" value={st.units_without_cluster || 0} bad />
            <StateChip label="Belum ada blok" value={st.units_without_block || 0} bad />
            <StateChip label="Cluster" value={st.clusters || 0} />
            <StateChip label="Blok" value={st.blocks || 0} />
            <StateChip label="Tipe unit" value={st.unit_types || 0} />
          </div>

          {runs.length === 0 ? (
            <p className="rounded-lg border border-dashed bg-secondary/40 px-3 py-3 text-xs text-muted-foreground">
              Belum ada catatan migrasi. Migrasi V2 berjalan otomatis saat backend dinyalakan.
            </p>
          ) : (
            <div className="space-y-2">
              {runs.map((r) => (
                <details key={r.id} data-testid={AUDIT.migrationRow} data-run={r.id}
                  className="rounded-lg border bg-background p-2.5">
                  <summary className="cursor-pointer text-sm">
                    <span className="font-medium">{r.name}</span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {formatDateTimeWIB(r.at)}
                    </span>
                  </summary>
                  <div className="mt-2 space-y-1 text-[11px] text-muted-foreground">
                    {runLines(r).map(([k, line]) => (
                      <div key={k}>
                        <span className="font-mono text-foreground">{k}</span> — {line}
                      </div>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
